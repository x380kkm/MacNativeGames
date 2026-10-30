/* Text entry for nn::swkbd::ShowKeyboard on iOS (the horse name, the first time the game asks).
   The guest thread blocks while the player types, as on the Mac (runtime/frontend.m); the alert is UIKit's own, so the
   system keyboard, the hardware keyboard and the paste menu all work. Nothing here is on the boot path: if no window is
   up, the request is cancelled and the game keeps its default (swkbd_host returns "cancelled"). */
#import <UIKit/UIKit.h>
#include <dispatch/dispatch.h>
#include <stdio.h>
#include <string.h>
#include "runtime.h"
#include "totk_ui_lang.h"

static UIViewController *top_view_controller(void) {
    UIWindow *key = nil;
    for (UIScene *scene in UIApplication.sharedApplication.connectedScenes)
        if ([scene isKindOfClass:UIWindowScene.class] && scene.activationState == UISceneActivationStateForegroundActive)
            for (UIWindow *window in ((UIWindowScene *)scene).windows)
                if (window.isKeyWindow) { key = window; break; }
    UIViewController *top = key.rootViewController;
    while (top.presentedViewController) top = top.presentedViewController;
    return top;
}

int runtime_front_text_input(const RuntimeTextRequest *req, char *out, size_t out_size) {
    if (!req || !out || !out_size) return 0;
    /* The guest calls this from its own thread; on the main thread the alert's answer could never arrive while we wait. */
    if (NSThread.isMainThread) { fprintf(stderr, "[totk] keyboard: asked on the main thread; cancelled\n"); return 0; }
    __block int confirmed = 0;
    __block NSString *entered = nil;
    __block UIAlertController *presented = nil;
    __block id sceneEnded = nil;   // the observer below, removed on the main queue once the guest has its answer
    dispatch_semaphore_t done = dispatch_semaphore_create(0);
    NSString *prompt = [NSString stringWithUTF8String:req->prompt ?: ""] ?: @"";
    NSString *initial = [NSString stringWithUTF8String:req->initial ?: ""] ?: @"";
    /* The alert's blocks can outlive the guest call (a timeout returns while it is still up): copy, never read req. */
    int minUnits = req->min_units, maxUnits = req->max_units;
    BOOL secure = req->secure != 0, digitsOnly = req->digits_only != 0;
    /* The hardware keyboard types into the alert; characters like J/K/Space must not also press game buttons. */
    runtime_keyboard_capture(1);

    dispatch_async(dispatch_get_main_queue(), ^{
        UIViewController *host = top_view_controller();
        if (!host || !host.view.window) {
            fprintf(stderr, "[totk] keyboard: no window for text entry; cancelled\n");
            dispatch_semaphore_signal(done);
            return;
        }
        UIAlertController *alert = [UIAlertController alertControllerWithTitle:prompt message:nil
                                                                preferredStyle:UIAlertControllerStyleAlert];
        __weak UIAlertController *weakAlert = alert;
        [alert addTextFieldWithConfigurationHandler:^(UITextField *field) {
            field.text = initial;
            field.secureTextEntry = secure;
            field.keyboardType = digitsOnly ? UIKeyboardTypeNumberPad : UIKeyboardTypeDefault;
            field.autocapitalizationType = UITextAutocapitalizationTypeNone;
            field.autocorrectionType = UITextAutocorrectionTypeNo;
        }];
        UIAlertAction *ok = [UIAlertAction actionWithTitle:@(TOTK_UI("确定", "OK")) style:UIAlertActionStyleDefault
                                                   handler:^(UIAlertAction *action) {
            (void)action;
            NSString *value = weakAlert.textFields.firstObject.text ?: @"";
            entered = value;
            confirmed = 1;
            dispatch_semaphore_signal(done);
        }];
        ok.enabled = initial.length >= (NSUInteger)minUnits;
        UITextField *field = alert.textFields.firstObject;
        [field addAction:[UIAction actionWithHandler:^(UIAction *action) {
            (void)action;
            if (maxUnits > 0 && (NSInteger)field.text.length > maxUnits) field.text = [field.text substringToIndex:maxUnits];
            ok.enabled = field.text.length >= (NSUInteger)minUnits;
        }] forControlEvents:UIControlEventEditingChanged];
        [alert addAction:[UIAlertAction actionWithTitle:@(TOTK_UI("取消", "Cancel")) style:UIAlertActionStyleCancel
                                               handler:^(UIAlertAction *action) {
            (void)action; dispatch_semaphore_signal(done);
        }]];
        [alert addAction:ok];
        presented = alert;
        /* The alert goes away with its window scene (the system can end a scene in the background), and nothing answers it
           then: cancelled at once instead of at the timeout, with the hardware keyboard given back to the game. */
        sceneEnded = [NSNotificationCenter.defaultCenter addObserverForName:UISceneDidDisconnectNotification
                                                                     object:host.view.window.windowScene
                                                                      queue:NSOperationQueue.mainQueue
                                                                 usingBlock:^(NSNotification *note) {
            (void)note;
            fprintf(stderr, "[totk] keyboard: the alert's window scene ended; cancelled\n");
            dispatch_semaphore_signal(done);
        }];
        [host presentViewController:alert animated:YES completion:^{
            if (host.presentedViewController != alert) {   /* another modal won: answer now instead of at the timeout */
                fprintf(stderr, "[totk] keyboard: the alert could not be shown; cancelled\n");
                dispatch_semaphore_signal(done);
                return;
            }
            fprintf(stderr, "[totk] keyboard: alert shown (%s, %d-%d characters)\n", prompt.UTF8String, minUnits, maxUnits);
        }];
    });
    /* A cancelled or unreachable alert must not hang the guest thread forever. */
    long timedOut = dispatch_semaphore_wait(done, dispatch_time(DISPATCH_TIME_NOW, 10 * 60 * NSEC_PER_SEC));
    runtime_keyboard_capture(0);
    dispatch_async(dispatch_get_main_queue(), ^{   // after the block above on the same queue, so the observer is set by now
        if (sceneEnded) [NSNotificationCenter.defaultCenter removeObserver:sceneEnded];
    });
    if (timedOut != 0) {
        fprintf(stderr, "[totk] keyboard: no answer after 10 minutes; cancelled\n");
        dispatch_async(dispatch_get_main_queue(), ^{   // do not leave a stale modal over a game that has moved on
            if (presented.presentingViewController) [presented dismissViewControllerAnimated:YES completion:nil];
        });
        return 0;
    }
    if (!confirmed) return 0;
    snprintf(out, out_size, "%s", entered.UTF8String ?: "");
    return 1;
}
