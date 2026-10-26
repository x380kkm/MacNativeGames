/* Motion aiming on iPhone and iPad (2026-10-26), restored from the 1.4.3 iPad build of 2026-10-22: its
   ios/Sources/motion_input.m (commit 30a1b93 plus local changes) was never committed. This file does what that build's
   code does, with the same settings keys, values and defaults, so a player's choices keep their meaning.
   Source: Settings › 體感來源 (TOTK_MOTION_SOURCE in the app's defaults: auto, controller, device or off; default auto,
   anything else counts as auto). TOTK_MOTION_SOURCE in the environment (devicectl --environment-variables) wins.
     controller  the first connected extended gamepad whose GCMotion has a rotation rate. Acceleration is gravity plus
                 user acceleration when the controller reports them apart. GCMotion's axes are the Switch's
                 (runtime/motion_fusion.c): the samples go in as they are and are never inverted.
     device      Core Motion's device motion, asked for 100 samples a second on the main queue (reference frame x
                 arbitrary, z vertical): acceleration = gravity + user acceleration in G and rotation rate in rad/s, on the
                 device's axes (in portrait x to the right, y to the top, z out of the screen) turned by the interface
                 orientation: upside down (-x, -y, z), landscape right (y, -x, z), landscape left (-y, x, z). A change
                 of orientation starts the fusion over (runtime_motion_start). Then Settings › 反轉本機體感上下
                 (TOTK_DEVICE_GYRO_INVERT_PITCH, default on; the environment variable wins, "0" off) negates the
                 rotation about x.
     auto        both; a device sample is dropped while the controller gave one within the last 500 ms.
     off         neither: the game sees a controller lying still.
   With these turns a landscape device held upright reads gravity as +1 G on y where the Switch reads -1 G
   (motion_fusion.c): its axes are turned by 180 degrees about z (derived from the documented axes of Core Motion and
   UIInterfaceOrientation, not measured). TOTK_GYRO_AXES (motion_fusion.c) applies to both sources on top of the turns;
   "-x,-y,z" together with TOTK_DEVICE_GYRO_INVERT_PITCH=0 gives the upright axes in landscape.
   A sample counts when its six values are finite and not all zero (GameController reports zeros for an 8BitDo in
   Switch mode: runtime/gamepad_feedback.m). The first sample of a source sets the dead zone default to 0 and marks the
   motion live, which starts the fusion over. The settings are read again when the app becomes active and when a
   controller connects or disconnects; while the app is inactive the sensors are off. Handlers of an earlier setup
   carry an older generation and are ignored. Nothing starts when the game has no six-axis sensor in the run
   (runtime_gyro_enabled, runtime/hid_feedback.c): TOTK_GYRO=0, or an agent's test session (TOTK_SLOT_OWNER claude /
   codex in the launch environment, which main.m keeps) without TOTK_GYRO=1. gyro.txt counts only when the launch
   environment names a TOTK_CONTROLS; the app sets none. Log lines "[ios-gyro]": the setup, each source's first sample,
   and one sample every 30 s. visionOS: no motion from here. */
#import "motion_input.h"
#include <TargetConditionals.h>

#if TARGET_OS_VISION
void runtime_ios_motion_start(UIView *view) { (void)view; }
#else
#import <CoreMotion/CoreMotion.h>
#import <GameController/GameController.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "runtime.h"

static NSString *const kSourceKey = @"TOTK_MOTION_SOURCE", *const kInvertKey = @"TOTK_DEVICE_GYRO_INVERT_PITCH";
static const uint64_t kControllerHoldNs = 500000000ull;   // auto: the device's samples wait this long after a controller's
static const uint64_t kReportNs = 30000000000ull;
static const NSTimeInterval kDeviceInterval = 0.01;   // seconds between device motion samples

/* Settings › Motion source, or TOTK_MOTION_SOURCE in the environment; auto unless one of the four words. */
static NSString *motion_source_setting(void) {
    const char *env = getenv("TOTK_MOTION_SOURCE");
    NSString *mode = env ? @(env) : [NSUserDefaults.standardUserDefaults stringForKey:kSourceKey];
    return mode && [@[@"auto", @"controller", @"device", @"off"] containsObject:mode] ? mode : @"auto";
}

/* Settings › Invert device up/down, or TOTK_DEVICE_GYRO_INVERT_PITCH in the environment ("0" or empty off). */
static BOOL invert_pitch_setting(void) {
    const char *env = getenv("TOTK_DEVICE_GYRO_INVERT_PITCH");
    return env ? (*env && strcmp(env, "0")) : [NSUserDefaults.standardUserDefaults boolForKey:kInvertKey];
}

static BOOL sample_usable(const double acc[3], const double gyro[3]) {
    BOOL moving = NO;
    for (int i = 0; i < 3; i++) {
        if (!isfinite(acc[i]) || !isfinite(gyro[i])) return NO;
        if (acc[i] != 0 || gyro[i] != 0) moving = YES;
    }
    return moving;
}

@interface TOTKMotionInput : NSObject
- (instancetype)initWithView:(UIView *)gameView;
- (void)resume;
- (void)pause;
- (void)configureWithout:(GCController *)leaving;
@end

/* Main thread only: the notifications, both sensor handlers and the samples they pass on run on the main queue. */
@implementation TOTKMotionInput {
    __weak UIView *view;
    CMMotionManager *device;
    GCController *controller;
    uint64_t generation;       // one more on each stop; a handler of an older setup does nothing
    uint64_t controllerLast;   // runtime_now_ns of the controller's latest usable sample, 0 = none since the setup
    uint64_t reportAt;
    UIInterfaceOrientation orientation;   // the one the device's samples are turned by
    BOOL active, live, invertPitch;
    const char *source;   // "controller" or "device" while live
}

- (instancetype)initWithView:(UIView *)gameView {
    if ((self = [super init])) {
        view = gameView;
        active = UIApplication.sharedApplication.applicationState == UIApplicationStateActive;
    }
    return self;
}

- (UIInterfaceOrientation)interfaceOrientation { return view.window.windowScene.effectiveGeometry.interfaceOrientation; }

- (void)resume { active = YES; [self configureWithout:nil]; }
- (void)pause { active = NO; [self stop]; }

- (void)stop {
    generation++;
    [device stopDeviceMotionUpdates];
    GCMotion *motion = controller.motion;
    motion.valueChangedHandler = nil;
    if (motion.sensorsRequireManualActivation) motion.sensorsActive = NO;
    controller = nil; controllerLast = 0; live = NO; source = NULL;
    runtime_motion_live(0);
}

/* The settings in force, from a fresh start. leaving: a controller that is disconnecting (still listed), or nil. */
- (void)configureWithout:(GCController *)leaving {
    [self stop];
    if (!active) return;
    NSString *mode = motion_source_setting();
    invertPitch = invert_pitch_setting();
    fprintf(stderr, "[ios-gyro] selected=%s invert-device-pitch=%d\n", mode.UTF8String, (int)invertPitch);
    if ([mode isEqualToString:@"off"]) return;
    if (![mode isEqualToString:@"device"]) [self startController:leaving];
    if (![mode isEqualToString:@"controller"]) [self startDevice];
}

- (void)startController:(GCController *)leaving {
    for (GCController *c in GCController.controllers)
        if (c != leaving && c.extendedGamepad && c.motion.hasRotationRate) { controller = c; break; }
    fprintf(stderr, "[ios-gyro] controller=%s\n", controller.vendorName.UTF8String ?: "no supported sensor");
    GCMotion *motion = controller.motion;
    if (!motion) return;
    if (motion.sensorsRequireManualActivation) motion.sensorsActive = YES;
    __weak TOTKMotionInput *weakSelf = self;
    const uint64_t setup = generation;
    motion.valueChangedHandler = ^(GCMotion *m) {
        GCAcceleration a = m.acceleration;
        if (m.hasGravityAndUserAcceleration) {
            GCAcceleration g = m.gravity, u = m.userAcceleration;
            a.x = g.x + u.x; a.y = g.y + u.y; a.z = g.z + u.z;
        }
        GCRotationRate r = m.rotationRate;
        dispatch_async(dispatch_get_main_queue(), ^{
            TOTKMotionInput *input = weakSelf;
            if (!input || input->generation != setup || !input->active) return;
            const double acc[3] = {a.x, a.y, a.z}, gyro[3] = {r.x, r.y, r.z};
            if (!sample_usable(acc, gyro)) return;
            input->controllerLast = runtime_now_ns();
            [input feed:acc gyro:gyro source:"controller"];
        });
    };
}

- (void)startDevice {
    if (!device) device = [CMMotionManager new];
    if (!device.deviceMotionAvailable) { fprintf(stderr, "[ios-gyro] device motion unavailable\n"); return; }
    device.deviceMotionUpdateInterval = kDeviceInterval;
    orientation = [self interfaceOrientation];
    __weak TOTKMotionInput *weakSelf = self;
    const uint64_t setup = generation;
    [device startDeviceMotionUpdatesUsingReferenceFrame:CMAttitudeReferenceFrameXArbitraryZVertical toQueue:NSOperationQueue.mainQueue
                                            withHandler:^(CMDeviceMotion *m, NSError *error) {
        TOTKMotionInput *input = weakSelf;
        if (!input || input->generation != setup || !input->active) return;
        if (error) { fprintf(stderr, "[ios-gyro] CoreMotion: %s\n", error.localizedDescription.UTF8String ?: "?"); return; }
        if (m) [input deviceSample:m];
    }];
}

/* One Core Motion sample on the turned axes the top of the file lists. */
- (void)deviceSample:(CMDeviceMotion *)m {
    if (controllerLast && runtime_now_ns() - controllerLast < kControllerHoldNs) return;
    UIInterfaceOrientation turn = [self interfaceOrientation];
    if (turn != orientation) { orientation = turn; runtime_motion_start(); }
    CMAcceleration g = m.gravity, u = m.userAcceleration;
    CMRotationRate r = m.rotationRate;
    const double x = g.x + u.x, y = g.y + u.y, z = g.z + u.z;
    double acc[3] = {x, y, z}, gyro[3] = {r.x, r.y, r.z};
    switch (turn) {
        case UIInterfaceOrientationPortraitUpsideDown: acc[0] = -x; acc[1] = -y; gyro[0] = -r.x; gyro[1] = -r.y; break;
        case UIInterfaceOrientationLandscapeRight: acc[0] = y; acc[1] = -x; gyro[0] = r.y; gyro[1] = -r.x; break;
        case UIInterfaceOrientationLandscapeLeft: acc[0] = -y; acc[1] = x; gyro[0] = -r.y; gyro[1] = r.x; break;
        default: break;   // portrait, or no window yet: the device's own axes
    }
    if (invertPitch) gyro[0] = -gyro[0];
    [self feed:acc gyro:gyro source:"device"];
}

- (void)feed:(const double *)acc gyro:(const double *)gyro source:(const char *)name {
    if (!sample_usable(acc, gyro)) return;
    if (!live || !source || strcmp(source, name)) {
        live = YES; source = name; reportAt = 0;
        runtime_motion_deadzone_default(0); runtime_motion_live(1);
        fprintf(stderr, "[ios-gyro] source=%s first valid sample\n", name);
    }
    uint64_t now = runtime_now_ns();
    runtime_motion_feed(acc, gyro, now);
    if (now - reportAt > kReportNs) {
        reportAt = now;
        fprintf(stderr, "[ios-gyro] %s acceleration=%.3f,%.3f,%.3f rotation=%.3f,%.3f,%.3f\n", name, acc[0], acc[1], acc[2], gyro[0], gyro[1], gyro[2]);
    }
}
@end

void runtime_ios_motion_start(UIView *view) {
    static TOTKMotionInput *input;
    if (input) return;
    if (!runtime_gyro_enabled()) { fprintf(stderr, "[ios-gyro] the game has no six-axis sensor in this run (TOTK_GYRO=0, or an agent's test session, TOTK_SLOT_OWNER claude / codex, without TOTK_GYRO=1): no motion\n"); return; }
    const char *axes = getenv("TOTK_GYRO_AXES");
    int remap = runtime_motion_axes(axes);
    if (remap < 0) runtime_fail("TOTK_GYRO_AXES must name x, y and z once each, e.g. \"-x,y,-z\"");
    if (remap > 0) fprintf(stderr, "[gyro] axes remapped by TOTK_GYRO_AXES=%s\n", axes);
    [NSUserDefaults.standardUserDefaults registerDefaults:@{kSourceKey: @"auto", kInvertKey: @YES}];   // Settings.bundle's defaults
    input = [[TOTKMotionInput alloc] initWithView:view];
    NSNotificationCenter *center = NSNotificationCenter.defaultCenter;
    NSOperationQueue *main = NSOperationQueue.mainQueue;
    [center addObserverForName:GCControllerDidConnectNotification object:nil queue:main usingBlock:^(NSNotification *note) {
        (void)note; [input configureWithout:nil];
    }];
    [center addObserverForName:GCControllerDidDisconnectNotification object:nil queue:main usingBlock:^(NSNotification *note) {
        [input configureWithout:note.object];
    }];
    [center addObserverForName:UIApplicationWillResignActiveNotification object:nil queue:main usingBlock:^(NSNotification *note) {
        (void)note; [input pause];
    }];
    [center addObserverForName:UIApplicationDidBecomeActiveNotification object:nil queue:main usingBlock:^(NSNotification *note) {
        (void)note; [input resume];
    }];
    [input configureWithout:nil];
}
#endif
