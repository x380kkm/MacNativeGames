#import <UIKit/UIKit.h>

/* Start screen (2026-10-26): where a run's settings are made, outside the game: the game's name and icon, its picture,
   shape, frame rate, durability and battery, and status lines, kept in the same defaults the Settings app writes, and a
   Start button. It shows only rows the game's Settings pane has. With the pane's custom layer on (TOTK_CUSTOM_PICTURE) the
   picture and the frame rate do not apply, so those two are left out and stay as they are.
   A pick is saved when it is made, and the rows show what the Settings app holds each time the app becomes active.
   Touch or a controller (up / down a row, left / right its value, A or the right face button to start). onStart runs
   once, on the main thread; the view removes itself. */
@interface TOTKStartView : UIView
- (instancetype)initWithFrame:(CGRect)frame onStart:(void (^)(void))onStart;
@end
