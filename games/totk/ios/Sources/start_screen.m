#import "start_screen.h"
#import <GameController/GameController.h>
#include "settings_map.h"
#include "totk_ui_lang.h"

static BOOL zh(void) { return totk_ui_zh(); }   // the language of the host's other text (boot screen, overlays; TOTK_UI_LANG overrides)
static NSString *T(NSString *z, NSString *e) { return zh() ? z : e; }

@implementation TOTKStartView {
    void (^_onStart)(void);
    UISegmentedControl *_picture, *_shape, *_fps, *_slot, *_status;
    UIButton *_start;
    NSArray<UIView *> *_rows;      // the controller's stops: the rows the screen shows, then Play
    NSArray<NSString *> *_slots;   // the pane's mod slots, in the order of _slot's segments
    NSInteger _row;          // the focused stop (controller)
    NSTimer *_poll;
    BOOL _held, _done;       // a controller button or direction held since the last poll
}

- (instancetype)initWithFrame:(CGRect)frame onStart:(void (^)(void))onStart {
    if (!(self = [super initWithFrame:frame])) return nil;
    _onStart = [onStart copy];
    self.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
    CAGradientLayer *bg = [CAGradientLayer layer];
    bg.colors = @[(id)[UIColor colorWithRed:0.10 green:0.11 blue:0.15 alpha:1].CGColor, (id)[UIColor colorWithRed:0.04 green:0.05 blue:0.07 alpha:1].CGColor];
    bg.frame = self.bounds; bg.needsDisplayOnBoundsChange = YES;
    [self.layer addSublayer:bg];

    NSString *name = [NSBundle.mainBundle objectForInfoDictionaryKey:@"CFBundleDisplayName"] ?: @"Game";

    UIImageView *icon = [[UIImageView alloc] initWithImage:[self appIcon]];
    icon.layer.cornerRadius = 28; icon.layer.cornerCurve = kCACornerCurveContinuous; icon.clipsToBounds = YES;
    icon.contentMode = UIViewContentModeScaleAspectFill; icon.backgroundColor = [UIColor colorWithWhite:1 alpha:0.08];
    [icon.widthAnchor constraintEqualToConstant:128].active = YES; [icon.heightAnchor constraintEqualToConstant:128].active = YES;
    icon.hidden = MIN(frame.size.width, frame.size.height) < 520;   // a phone's height holds the rows without it

    UILabel *title = [UILabel new];
    title.text = name; title.font = [UIFont systemFontOfSize:34 weight:UIFontWeightBold]; title.textColor = UIColor.whiteColor;
    title.adjustsFontSizeToFitWidth = YES; title.minimumScaleFactor = 0.6;

    NSMutableArray<NSString *> *pictures = [NSMutableArray arrayWithObjects:T(@"720p（掌机）", @"720p (handheld)"), T(@"1080p（底座）", @"1080p (docked)"), nil];
    if ([self settingsPaneHas:@"TOTK_NATIVE_PICTURE"]) [pictures addObject:T(@"高清（设备屏幕）", @"HD (device screen)")];
    _picture = [[UISegmentedControl alloc] initWithItems:pictures];
    _shape = [[UISegmentedControl alloc] initWithItems:@[@"16:9", T(@"全屏", @"Full screen")]];
    _fps = [[UISegmentedControl alloc] initWithItems:@[@"30 fps", @"60 fps"]];
    _slots = @[@"off", @"moderate", @"strong", @"max"];
    _slot = [[UISegmentedControl alloc] initWithItems:@[T(@"关", @"Off"), T(@"中", @"Moderate"), T(@"强", @"Strong"), T(@"最大", @"Max")]];
    _status = [[UISegmentedControl alloc] initWithItems:@[T(@"关", @"Off"), T(@"开", @"On")]];
    [self showStoredRows];
    [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(showStoredRows) name:UIApplicationDidBecomeActiveNotification object:nil];
    for (UISegmentedControl *s in @[_picture, _shape, _fps, _slot, _status]) {
        s.overrideUserInterfaceStyle = UIUserInterfaceStyleDark;
        [s.widthAnchor constraintEqualToConstant:440].active = YES;
        [s addTarget:self action:@selector(changed:) forControlEvents:UIControlEventValueChanged];
    }

    UIButtonConfiguration *cfg = [UIButtonConfiguration filledButtonConfiguration];
    cfg.title = T(@"开始游戏", @"Play"); cfg.image = [UIImage systemImageNamed:@"play.fill"]; cfg.imagePadding = 8;
    cfg.baseBackgroundColor = [UIColor colorWithRed:0.10 green:0.63 blue:1.0 alpha:1]; cfg.cornerStyle = UIButtonConfigurationCornerStyleCapsule;
    cfg.contentInsets = NSDirectionalEdgeInsetsMake(14, 40, 14, 40);
    cfg.titleTextAttributesTransformer = ^NSDictionary *(NSDictionary *a) {
        NSMutableDictionary *m = a.mutableCopy; m[NSFontAttributeName] = [UIFont systemFontOfSize:20 weight:UIFontWeightSemibold]; return m; };
    _start = [UIButton buttonWithConfiguration:cfg primaryAction:[UIAction actionWithHandler:^(UIAction *a) { (void)a; [self start]; }]];

    /* A row shows only what the pane has. The presets do not apply with the custom layer on (apply_display_settings), so
       their two rows stay out then and what they hold is left as it is. */
    BOOL presets = !totk_custom_layer;
    NSMutableArray<UIView *> *stops = [NSMutableArray array], *shown = [NSMutableArray arrayWithObjects:icon, title, nil];
    void (^add)(NSString *, UISegmentedControl *) = ^(NSString *label, UISegmentedControl *control) {
        [stops addObject:control]; [shown addObject:[self row:label control:control]];
    };
    if (presets && [self settingsPaneHas:@"TOTK_DOCKED"]) add(T(@"画面", @"Picture"), _picture);
    if ([self settingsPaneHas:@"TOTK_FILL_SCREEN"]) add(T(@"比例", @"Shape"), _shape);
    if (presets) add(T(@"帧率", @"Frame rate"), _fps);
    if ([self settingsPaneHas:@"TOTK_MOD_SLOT"]) add(T(@"耐久与电池", @"Durability"), _slot);
    add(T(@"状态显示", @"Status"), _status);
    UIView *lastRow = shown.lastObject;
    [stops addObject:_start]; [shown addObject:_start];
    _rows = stops; _row = (NSInteger)stops.count - 1;

    UIStackView *stack = [[UIStackView alloc] initWithArrangedSubviews:shown];
    stack.axis = UILayoutConstraintAxisVertical; stack.alignment = UIStackViewAlignmentCenter; stack.spacing = 18;
    [stack setCustomSpacing:28 afterView:title]; [stack setCustomSpacing:26 afterView:lastRow];
    stack.translatesAutoresizingMaskIntoConstraints = NO;
    [self addSubview:stack];
    [NSLayoutConstraint activateConstraints:@[[stack.centerXAnchor constraintEqualToAnchor:self.centerXAnchor],
                                              [stack.centerYAnchor constraintEqualToAnchor:self.centerYAnchor],
                                              [stack.leadingAnchor constraintGreaterThanOrEqualToAnchor:self.safeAreaLayoutGuide.leadingAnchor constant:24]]];
    [self focus];
    __weak TOTKStartView *weak = self;
    _poll = [NSTimer scheduledTimerWithTimeInterval:1.0 / 60 repeats:YES block:^(NSTimer *t) { (void)t; [weak pollController]; }];
    return self;
}

/* The rows as the defaults hold them. The Settings app can change those while this screen is up, since iOS keeps the app
   alive behind it, so they are read again each time the app becomes active. */
- (void)showStoredRows {
    NSUserDefaults *d = NSUserDefaults.standardUserDefaults;
    _picture.selectedSegmentIndex = [d boolForKey:@"TOTK_NATIVE_PICTURE"] && _picture.numberOfSegments > 2 ? 2 : [d boolForKey:@"TOTK_DOCKED"] ? 1 : 0;
    _shape.selectedSegmentIndex = [d boolForKey:@"TOTK_FILL_SCREEN"] ? 1 : 0;
    _fps.selectedSegmentIndex = [[d stringForKey:@"TOTK_PHONE_FPS"] isEqualToString:@"30"] ? 0 : 1;
    NSUInteger slot = [_slots indexOfObject:[d stringForKey:@"TOTK_MOD_SLOT"] ?: @""];
    _slot.selectedSegmentIndex = slot == NSNotFound ? 0 : (NSInteger)slot;
    _status.selectedSegmentIndex = [d boolForKey:@"TOTK_FPS_OVERLAY"] ? 1 : 0;
}

/* Whether the app's Settings pane offers a setting: the start screen shows only what the Settings app has. */
- (BOOL)settingsPaneHas:(NSString *)key {
    NSString *path = [NSBundle.mainBundle pathForResource:@"Root" ofType:@"plist" inDirectory:@"Settings.bundle"];
    for (NSDictionary *spec in [NSDictionary dictionaryWithContentsOfFile:path][@"PreferenceSpecifiers"] ?: @[])
        if ([spec[@"Key"] isEqualToString:key]) return YES;
    return NO;
}

- (void)layoutSubviews { [super layoutSubviews]; self.layer.sublayers.firstObject.frame = self.bounds; }

- (UIStackView *)row:(NSString *)label control:(UIView *)control {
    UILabel *l = [UILabel new];
    l.text = label; l.font = [UIFont systemFontOfSize:17 weight:UIFontWeightMedium]; l.textColor = [UIColor colorWithWhite:0.85 alpha:1];
    l.adjustsFontSizeToFitWidth = YES; l.minimumScaleFactor = 0.7;
    [l.widthAnchor constraintEqualToConstant:100].active = YES;
    UIStackView *s = [[UIStackView alloc] initWithArrangedSubviews:@[l, control]];
    s.spacing = 16; s.alignment = UIStackViewAlignmentCenter;
    return s;
}

/* The home screen icon the build put in the app (build_ipa.py: the game's own). */
- (UIImage *)appIcon {
    NSDictionary *icons = [NSBundle.mainBundle objectForInfoDictionaryKey:@"CFBundleIcons"];
    NSString *file = [icons[@"CFBundlePrimaryIcon"][@"CFBundleIconFiles"] lastObject];
    UIImage *image = file ? [UIImage imageNamed:file] : nil;
    return image ?: [UIImage imageNamed:@"AppIcon"] ?: [UIImage systemImageNamed:@"gamecontroller.fill"];
}

/* A pick is saved when it is made, that row alone, and Play saves nothing: what the screen shows can be older than what is
   stored, and writing it back would undo a change made in the Settings app. */
- (void)changed:(UISegmentedControl *)s {
    NSUserDefaults *d = NSUserDefaults.standardUserDefaults;
    NSInteger i = s.selectedSegmentIndex;
    if (s == _picture) { [d setBool:i > 0 forKey:@"TOTK_DOCKED"]; [d setBool:i > 1 forKey:@"TOTK_NATIVE_PICTURE"]; }
    else if (s == _shape) [d setBool:i == 1 forKey:@"TOTK_FILL_SCREEN"];
    else if (s == _fps) [d setObject:i == 0 ? @"30" : @"60" forKey:@"TOTK_PHONE_FPS"];
    else if (s == _slot) [d setObject:_slots[(NSUInteger)i] forKey:@"TOTK_MOD_SLOT"];
    else { [d setBool:i == 1 forKey:@"TOTK_FPS_OVERLAY"]; [d setBool:i == 1 forKey:@"TOTK_SHADER_OVERLAY"]; }
}

- (void)start {
    if (_done) return;
    _done = YES;
    [_poll invalidate]; _poll = nil;
    [NSNotificationCenter.defaultCenter removeObserver:self];
    void (^go)(void) = _onStart; _onStart = nil;
    [UIView animateWithDuration:0.25 animations:^{ self.alpha = 0; } completion:^(BOOL f) { (void)f; [self removeFromSuperview]; }];
    if (go) go();
}

/* The controller's focus: a ring around the row it moves. */
- (void)focus {
    for (NSUInteger i = 0; i < _rows.count; i++) {
        _rows[i].layer.borderWidth = (NSInteger)i == _row ? 2 : 0;
        _rows[i].layer.borderColor = [UIColor colorWithRed:0.10 green:0.63 blue:1.0 alpha:1].CGColor;
        _rows[i].layer.cornerRadius = _rows[i] == _start ? 26 : 9;
    }
}

- (void)pollController {
    GCExtendedGamepad *g = GCController.current.extendedGamepad ?: GCController.controllers.firstObject.extendedGamepad;
    if (!g) return;
    float x = g.leftThumbstick.xAxis.value, y = g.leftThumbstick.yAxis.value;
    BOOL up = g.dpad.up.isPressed || y > 0.5, down = g.dpad.down.isPressed || y < -0.5;
    BOOL left = g.dpad.left.isPressed || x < -0.5, right = g.dpad.right.isPressed || x > 0.5;
    BOOL confirm = g.buttonA.isPressed || g.buttonMenu.isPressed;   // A or the menu button; B is back, never "Play" (after PR #1174)
    BOOL any = up || down || left || right || confirm;
    if (!any) { _held = NO; return; }
    if (_held) return;
    _held = YES;
    NSInteger play = (NSInteger)_rows.count - 1;
    if (up) _row = MAX(0, _row - 1);
    else if (down) _row = MIN(play, _row + 1);
    else if ((left || right) && _row < play) {
        UISegmentedControl *s = (UISegmentedControl *)_rows[(NSUInteger)_row];
        s.selectedSegmentIndex = MAX(0, MIN((NSInteger)s.numberOfSegments - 1, s.selectedSegmentIndex + (right ? 1 : -1)));
        [self changed:s];
    } else if (confirm && _row == play) { [self start]; return; }
    else if (confirm) _row = play;
    [self focus];
}
@end
