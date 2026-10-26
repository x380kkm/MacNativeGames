#import <UIKit/UIKit.h>

/* Motion aiming on iPhone and iPad: the device's own gyro (Core Motion) or a connected controller's (GameController),
   as Settings › Motion source chooses, fed to runtime/motion_fusion.c for the game's six-axis sensor. view is the game's
   view; its window scene gives the interface orientation the device's axes are turned by. Main thread, once, before
   the game starts (Sources/main.m startGame). */
void runtime_ios_motion_start(UIView *view);
