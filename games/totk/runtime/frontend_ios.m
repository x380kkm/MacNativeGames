/* Native iOS view and VI service adapter: the iPhone counterpart of frontend.m (same exported functions).
   The app (ios/app/Sources/main.m) owns UIKit: it creates the full-screen Metal view, hands its layer over with
   runtime_ios_attach_layer, and calls the loader's main on a game thread. No guest frame is synthesized. */
#import <UIKit/UIKit.h>
#import <QuartzCore/CAMetalLayer.h>
#import <Metal/Metal.h>
#include <stdatomic.h>
#include <unistd.h>
#include "runtime.h"
#include "totk_ui_lang.h"
static CAMetalLayer *metalLayer;
static __weak UIView *hostView;   /* the game's view (runtime_ios_attach_layer); the text entry box falls back to its window */
static UIView *bootOverlay;
static UILabel *bootStage,*bootDetail;
static UIProgressView *bootProgress;
static uint64_t bootStartNS;
static _Atomic uint64_t presentedFrames;
static CADisplayLink *displayLink;
static pthread_mutex_t vsyncLock=PTHREAD_MUTEX_INITIALIZER;
static void *vsyncEvents[16];
static unsigned vsyncCount;
void hle_bind_system_event(void *,int);
void hle_signal_system_event(void *);
void *front_metal_layer(void){return (__bridge void *)metalLayer;}
void front_frame_presented(void){
 if(atomic_fetch_add_explicit(&presentedFrames,1,memory_order_relaxed)==0){
  fprintf(stderr,"[totk-boot] %.3f first presented frame\n",(runtime_now_ns()-bootStartNS)/1e9);
  dispatch_async(dispatch_get_main_queue(), ^{bootOverlay.hidden=YES;});
 }
}
void runtime_boot_progress(const char *stage,uint64_t done,uint64_t total){
 static const char *last;
 if(stage!=last){fprintf(stderr,"[totk-boot] %.3f %s\n",bootStartNS?(runtime_now_ns()-bootStartNS)/1e9:0,stage?stage:"startup");last=stage;}
 NSString *s=[NSString stringWithUTF8String:stage?stage:TOTK_UI("正在启动","Starting")];
 dispatch_async(dispatch_get_main_queue(), ^{
  if(!bootOverlay||bootOverlay.hidden)return;
  bootStage.text=s;
  if(total){bootDetail.text=[NSString stringWithFormat:@"%.1f / %.1f GB",done/1e9,total/1e9];bootProgress.hidden=NO;bootProgress.progress=(float)((double)done/(double)total);}
  else {bootDetail.text=@(TOTK_UI("正在处理，请稍候","Working, please wait"));bootProgress.hidden=YES;}
 });
}
void runtime_boot_count(const char *stage,uint64_t done,uint64_t total){
 /* Steps counted in items, not bytes (the shader import: tens of thousands of files, minutes on a phone). */
 static const char *last;
 if(stage!=last){fprintf(stderr,"[totk-boot] %.3f %s\n",bootStartNS?(runtime_now_ns()-bootStartNS)/1e9:0,stage?stage:"startup");last=stage;}
 NSString *s=[NSString stringWithUTF8String:stage?stage:TOTK_UI("正在启动","Starting")];
 dispatch_async(dispatch_get_main_queue(), ^{
  if(!bootOverlay||bootOverlay.hidden)return;
  bootStage.text=s;bootDetail.text=[NSString stringWithFormat:@"%llu / %llu",(unsigned long long)done,(unsigned long long)total];
  if(total){bootProgress.hidden=NO;bootProgress.progress=(float)((double)done/(double)total);}
 });
}
void runtime_boot_status(const char *stage,const char *detail){
 if(bootStartNS)fprintf(stderr,"[totk-boot] %.3f %s — %s\n",(runtime_now_ns()-bootStartNS)/1e9,stage?stage:"startup",detail?detail:"");
 NSString *s=[NSString stringWithUTF8String:stage?stage:TOTK_UI("正在启动","Starting")];
 NSString *d=[NSString stringWithUTF8String:detail?detail:TOTK_UI("正在处理，请稍候","Working, please wait")];
 dispatch_async(dispatch_get_main_queue(), ^{if(!bootOverlay||bootOverlay.hidden)return;bootStage.text=s;bootDetail.text=d;bootProgress.hidden=YES;});
}
/* Background shader/pipeline warm-up progress (iOS ships with the warm manifest off, but the hooks are shared with the Mac front end). */
void runtime_warm_progress(uint64_t done,uint64_t total,uint64_t shaders,uint64_t shader_total,uint64_t pipelines,uint64_t pipeline_total){
 (void)shaders;(void)shader_total;(void)pipelines;(void)pipeline_total;
 dispatch_async(dispatch_get_main_queue(), ^{
  if(!bootOverlay||bootOverlay.hidden)return;
  double frac=total ? fmin(1.0,(double)done/(double)total) : 1.0;
  bootStage.text=[NSString stringWithFormat:@(TOTK_UI("预热着色器与管线 %.0f%%","Warming shaders and pipelines %.0f%%")),floor(frac*100.0)];
  bootDetail.text=[NSString stringWithFormat:@(TOTK_UI("已处理 %llu/%llu 项","%llu/%llu items")),(unsigned long long)done,(unsigned long long)total];
  bootProgress.hidden=NO;bootProgress.progress=(float)frac;
 });
}
void runtime_warm_done(void){}
/* The "温控" of the present lines (hle_nvn.c): the system's thermal state, 0 nominal, 1 fair, 2 serious, 3 critical; the default
   (-1) was never replaced on iOS, so a phone slowing down as it warmed could not be told from other causes (2026-10-23). */
int dm_thermal_now(void){return (int)NSProcessInfo.processInfo.thermalState;}
uint64_t front_game_res(int docked){(void)docked;return (720ULL<<32)|1280;}
static _Atomic int appActive=1;
int runtime_front_focus(void){return atomic_load(&appActive);}
void mtl_app_active(int active);
void mtl_hud_safe_area(int w,int h,int side,int bottom);   /* gfx/nvn/nvn_mtl.m: the HUD boxes keep out of the safe area */
void runtime_ios_sync_safe_area(UIView *host);
/* Not active (background, Control Center, lock): stop GPU submission (iOS rejects background GPU work) and tell the game focus changed, like the Mac window. */
static void app_active_changed(int active){
 if(atomic_exchange(&appActive,active)==active)return;
 if(!active)runtime_input_clear();
 mtl_app_active(active);runtime_oe_push_message(15);
 fprintf(stderr,"[totk] app %s\n",active?"became active":"resigned active: GPU submission paused");
}
void runtime_front_request_close(void){fprintf(stderr,"[totk] close requested; iOS apps are closed by the user\n");}

/* The display link's rate, which paces the game (mtl_display_hz): 60 on every iPhone / iPad, also a ProMotion one, whose
   screen reports 120 (UIScreen.maximumFramesPerSecond with CADisableMinimumFrameDurationOnPhone). */
#define TOTK_IOS_LINK_HZ 60
int front_display_link_hz(void){return TOTK_IOS_LINK_HZ;}

@interface TOTKVsync:NSObject
@end
@implementation TOTKVsync
-(void)tick:(CADisplayLink *)l{(void)l;pthread_mutex_lock(&vsyncLock);for(unsigned i=0;i<vsyncCount;i++)hle_signal_system_event(vsyncEvents[i]);pthread_mutex_unlock(&vsyncLock);}
@end
static TOTKVsync *vsyncTarget;

/* visionOS windows resize after launch; keep the drawable and camera aspect in step with the view. */
void runtime_ios_sync_drawable(UIView *host){
 if(!metalLayer||host.bounds.size.width<1||host.bounds.size.height<1)return;
#if TARGET_OS_VISION
 CGFloat s=host.traitCollection.displayScale>0?host.traitCollection.displayScale:2;
#else
 CGFloat s=host.window.screen.nativeScale>0?host.window.screen.nativeScale:UIScreen.mainScreen.nativeScale;
#endif
 metalLayer.contentsScale=s;
 /* TOTK_IOS_DRAWABLE_H (default 720; 0 = native pixels): build the drawable this many pixels tall at the view's aspect, so the
    game picture (1280x720 canvas) lands about 1:1 and the system compositor scales it to the screen instead of our GPU. */
 double vw=round(host.bounds.size.width*s),vh=round(host.bounds.size.height*s);
 const char *dh=getenv("TOTK_IOS_DRAWABLE_H");long want=dh?strtol(dh,NULL,10):720;
 /* the 16:9 picture should get about want rows: a screen narrower than 16:9 (an iPad, about 4:3; 2026-10-17) holds it by
    width, so there the drawable is want*16/9 columns wide (1281x890 on a 2360x1640 iPad); an iPhone keeps want rows */
 if(want>0){double h=vw/vh<16.0/9.0?round(want*16.0/9.0*vh/vw):(double)want;if(h<vh){vw=round(vw*h/vh);vh=h;}}
 if(CGSizeEqualToSize(metalLayer.drawableSize,CGSizeMake(vw,vh)))return;
 metalLayer.drawableSize=CGSizeMake(vw,vh);
 fprintf(stderr,"[totk] view drawable %.0fx%.0f (screen scale %.1f, TOTK_IOS_DRAWABLE_H=%ld)\n",vw,vh,s,want);runtime_aspect_view(vw,vh);   /* full screen: the camera takes the drawable's shape (aspect_patch.h) */
 runtime_ios_sync_safe_area(host);
}
/* The safe area (notch, rounded corners, home indicator) in drawable pixels: the HUD's corner boxes keep out of it
   (nvn_mtl.m). The view's safeAreaInsetsDidChange calls it too: at the first drawable the view is in no window yet and
   the insets are 0. */
void runtime_ios_sync_safe_area(UIView *host){
 CGSize px=metalLayer?metalLayer.drawableSize:CGSizeZero;
 if(px.width<1||host.bounds.size.width<1)return;
 UIEdgeInsets in=host.safeAreaInsets;double k=px.width/host.bounds.size.width;   /* points -> drawable pixels */
 mtl_hud_safe_area((int)px.width,(int)px.height,(int)lround(MAX(in.left,in.right)*k),(int)lround(in.bottom*k));
}

/* Called on the main thread by the app before the game thread starts. */
void runtime_ios_attach_layer(CAMetalLayer *layer,UIView *host){
 bootStartNS=runtime_now_ns();hostView=host;
 metalLayer=layer;metalLayer.device=MTLCreateSystemDefaultDevice();metalLayer.pixelFormat=MTLPixelFormatBGRA8Unorm;metalLayer.framebufferOnly=NO;
 runtime_ios_sync_drawable(host);
 bootOverlay=[[UIView alloc] initWithFrame:host.bounds];bootOverlay.autoresizingMask=UIViewAutoresizingFlexibleWidth|UIViewAutoresizingFlexibleHeight;
 bootOverlay.backgroundColor=[UIColor colorWithRed:0.035 green:0.075 blue:0.09 alpha:1];
 CGFloat w=host.bounds.size.width,h=host.bounds.size.height;
 bootStage=[[UILabel alloc] initWithFrame:CGRectMake(0,h/2-50,w,36)];bootStage.text=@(TOTK_UI("正在启动海拉鲁","Starting Hyrule"));bootStage.textColor=UIColor.whiteColor;
 bootStage.font=[UIFont systemFontOfSize:24 weight:UIFontWeightSemibold];bootStage.textAlignment=NSTextAlignmentCenter;
 bootDetail=[[UILabel alloc] initWithFrame:CGRectMake(24,h/2-8,w-48,36)];bootDetail.text=@(TOTK_UI("正在准备游戏环境","Preparing the game environment"));bootDetail.textColor=[UIColor colorWithWhite:0.72 alpha:1];
 bootDetail.font=[UIFont systemFontOfSize:14];bootDetail.textAlignment=NSTextAlignmentCenter;
 bootDetail.numberOfLines=2;bootDetail.adjustsFontSizeToFitWidth=YES;bootDetail.minimumScaleFactor=0.6;   /* a message (no game data) fits in two lines */
 bootProgress=[[UIProgressView alloc] initWithFrame:CGRectMake(w/2-140,h/2+30,280,8)];bootProgress.hidden=YES;
 [bootOverlay addSubview:bootStage];[bootOverlay addSubview:bootDetail];[bootOverlay addSubview:bootProgress];[host addSubview:bootOverlay];
 NSNotificationCenter *nc=NSNotificationCenter.defaultCenter;
 [nc addObserverForName:UIApplicationWillResignActiveNotification object:nil queue:nil usingBlock:^(NSNotification *n){(void)n;app_active_changed(0);}];
 [nc addObserverForName:UIApplicationDidBecomeActiveNotification object:nil queue:nil usingBlock:^(NSNotification *n){(void)n;app_active_changed(1);}];
 vsyncTarget=[TOTKVsync new];displayLink=[CADisplayLink displayLinkWithTarget:vsyncTarget selector:@selector(tick:)];
 displayLink.preferredFrameRateRange=CAFrameRateRangeMake(TOTK_IOS_LINK_HZ,TOTK_IOS_LINK_HZ,TOTK_IOS_LINK_HZ);[displayLink addToRunLoop:NSRunLoop.mainRunLoop forMode:NSRunLoopCommonModes];
}
/* The app already runs the loader on a game thread with a large stack; the event loop belongs to UIKit. */
void runtime_front_run(void(*callback)(void)){
 if(!metalLayer)runtime_fail("iOS view not attached before boot");
 runtime_gamepad_start();
 @autoreleasepool{callback();}
}
/* Text entry for the game (nn::swkbd::ShowKeyboard, runtime/swkbd_host.c; TOTK names a horse with it), the counterpart of
   the Mac's bar (frontend.m). A box (an alert with one text field) opens over the game: its title is the request's title
   (the game's header text, else its guide text or a default), its message the request's detail (the guide text under a
   header) and the length limit. The field starts with the game's initial text, offers the number pad for a number
   request and hides a password. The on-screen keyboard or a hardware one types, input methods included; OK or Return
   confirms, Cancel or Escape cancels. Characters the game disallows and text beyond its length limit are removed as
   they are typed, but not while an input method is still composing (the caller checks again). OK is off while the
   text is empty or too short, and Return then does nothing, as on the Mac. The box is presented by the
   topmost view controller of the key window of the scene in front, so the touch controls (a view under it) get none of
   its touches. The calling guest thread waits on a semaphore; the game's input is cleared when the box opens and again
   when it closes, so a controller button pressed while typing does not reach the game afterwards.
   TOTK_IOS_TEXT_ENTRY=0 cancels every request without the box, as all iOS builds did before 2026-10-26. */
static int text_entry_enabled(void){const char *e=getenv("TOTK_IOS_TEXT_ENTRY");return !(e&&!strcmp(e,"0"));}
/* The view controller that presents the box: the topmost one of the key window of the scene in front; when no scene is in
   front (Control Center, a call), the game's own window, so the box is there on return. */
static UIViewController *text_entry_presenter(void){
 UIWindow *key=nil;
 for(UIScene *scene in UIApplication.sharedApplication.connectedScenes){
  if(scene.activationState!=UISceneActivationStateForegroundActive||![scene isKindOfClass:UIWindowScene.class])continue;
  key=((UIWindowScene *)scene).keyWindow;
  if(key)break;
 }
 if(!key)key=hostView.window;
 UIViewController *top=key.rootViewController;
 while(top.presentedViewController&&![top.presentedViewController isBeingDismissed])top=top.presentedViewController;
 return top;
}
@interface TOTKTextEntry:NSObject<UITextFieldDelegate>
@property(nonatomic,weak) UIAlertController *alert;   /* the presentation keeps it; it keeps this entry through its actions */
@property(nonatomic,weak) UITextField *field;
@property(nonatomic,weak) UIAlertAction *ok;
@property(nonatomic,copy) NSString *heading,*detail,*text;   /* text: what the field starts with */
@property(nonatomic) int maxUnits,minUnits,digitsOnly,secure,attempts;
@property(nonatomic) uint32_t disabled;
@property(nonatomic,copy) void(^done)(NSString *text);   /* nil text: cancelled; the property is nil once answered */
-(void)show;
-(void)refilter;
-(NSString *)current;
-(BOOL)confirm;
-(void)finish:(NSString *)text;
@end
static __weak TOTKTextEntry *openEntry;   /* main thread only: the box the diagnostics act on */
@implementation TOTKTextEntry
-(BOOL)allowed:(unichar)c{
 BOOL digit=c>='0'&&c<='9';uint32_t d=self.disabled;
 if(self.digitsOnly&&!digit)return NO;
 if(c<0x20||c==0x7f)return NO;
 if((d&1u<<1&&c==' ')||(d&1u<<2&&c=='@')||(d&1u<<3&&c=='%')||(d&1u<<4&&c=='/')||(d&1u<<5&&c=='\\')||(d&1u<<6&&digit))return NO;
 return YES;
}
/* The game's limits on s: disallowed characters dropped, cut to max_units UTF-16 units between two characters. */
-(NSString *)filtered:(NSString *)s{
 NSMutableString *t=[NSMutableString string];
 [s enumerateSubstringsInRange:NSMakeRange(0,s.length) options:NSStringEnumerationByComposedCharacterSequences usingBlock:^(NSString *sub,NSRange r,NSRange er,BOOL *stop){
  (void)r;(void)er;
  if(sub.length==1&&![self allowed:[sub characterAtIndex:0]])return;
  if(self.maxUnits>0&&t.length+sub.length>(NSUInteger)self.maxUnits){*stop=YES;return;}
  [t appendString:sub];}];
 return t;
}
-(NSString *)current{UITextField *f=self.field;return (f?f.text:self.text)?:@"";}
-(int)shortest{return self.minUnits>1?self.minUnits:1;}   /* an empty answer is none (the Mac bar beeps at it) */
-(void)updateOK{self.ok.enabled=(int)[self filtered:[self current]].length>=[self shortest];}
-(void)refilter{
 UITextField *f=self.field;
 if(f&&!f.markedTextRange){NSString *s=f.text?:@"",*t=[self filtered:s];if(![t isEqualToString:s])f.text=t;}
 [self updateOK];
}
-(void)edited:(UITextField *)f{(void)f;[self refilter];}
-(BOOL)textFieldShouldReturn:(UITextField *)f{(void)f;[self confirm];return NO;}   /* Return on either keyboard */
-(void)configure:(UITextField *)f{
 f.text=[self filtered:self.text?:@""];
 f.secureTextEntry=self.secure!=0;
 f.keyboardType=self.digitsOnly?UIKeyboardTypeASCIICapableNumberPad:UIKeyboardTypeDefault;
 f.returnKeyType=UIReturnKeyDone;f.enablesReturnKeyAutomatically=YES;
 f.autocorrectionType=UITextAutocorrectionTypeNo;f.spellCheckingType=UITextSpellCheckingTypeNo;   /* a name is not corrected */
 f.autocapitalizationType=UITextAutocapitalizationTypeWords;f.clearButtonMode=UITextFieldViewModeWhileEditing;
 f.delegate=self;[f addTarget:self action:@selector(edited:) forControlEvents:UIControlEventEditingChanged];
 self.field=f;
}
-(void)show{
 UIViewController *top=text_entry_presenter();
 if(!top){fprintf(stderr,"[totk] keyboard: no window for the text entry box; cancelled\n");[self finish:nil];return;}
 NSString *limit=self.maxUnits>0?[NSString stringWithFormat:@(TOTK_UI("最多 %d 个字","Up to %d characters")),self.maxUnits]:@"";
 NSString *message=!self.detail.length?limit:!limit.length?self.detail:[NSString stringWithFormat:@"%@\n%@",self.detail,limit];
 UIAlertController *alert=[UIAlertController alertControllerWithTitle:self.heading message:message.length?message:nil preferredStyle:UIAlertControllerStyleAlert];
 [alert addTextFieldWithConfigurationHandler:^(UITextField *f){[self configure:f];}];
 [alert addAction:[UIAlertAction actionWithTitle:@(TOTK_UI("取消","Cancel")) style:UIAlertActionStyleCancel handler:^(UIAlertAction *a){(void)a;[self finish:nil];}]];
 /* UIKit closes the alert for OK whatever its handler does: a text that the last composed characters left too short opens
    the box again */
 UIAlertAction *ok=[UIAlertAction actionWithTitle:@(TOTK_UI("确定","OK")) style:UIAlertActionStyleDefault handler:^(UIAlertAction *a){(void)a;
  if(![self confirm]){self.text=[self current];[self show];}}];
 [alert addAction:ok];alert.preferredAction=ok;   /* Return on a hardware keyboard */
 self.alert=alert;self.ok=ok;[self updateOK];
 [top presentViewController:alert animated:YES completion:nil];
 fprintf(stderr,"[totk] keyboard: text entry box shown (%s%s%s)\n",self.heading.UTF8String?:"",self.detail.length?" — ":"",self.detail.UTF8String?:"");
 dispatch_after(dispatch_time(DISPATCH_TIME_NOW,NSEC_PER_SEC),dispatch_get_main_queue(),^{[self checkShown];});
}
/* A presentation UIKit refuses (another one still in progress) leaves the box unseen and the game waiting: try again, five
   times in all, then cancel. */
-(void)checkShown{
 if(!self.done||self.alert.presentingViewController)return;   /* answered, or on the screen */
 if(++self.attempts<5){fprintf(stderr,"[totk] keyboard: the text entry box did not appear; trying again\n");[self show];return;}
 fprintf(stderr,"[totk] keyboard: the text entry box could not be shown; cancelled\n");[self finish:nil];
}
/* OK, Return or "kbenter": the text with the game's limits applied; empty or too short does nothing. */
-(BOOL)confirm{
 NSString *s=[self filtered:[self current]];
 if((int)s.length<[self shortest]){fprintf(stderr,"[totk] keyboard: %d characters, at least %d needed; the box stays\n",(int)s.length,[self shortest]);return NO;}
 [self finish:s];return YES;
}
-(void)finish:(NSString *)text{
 void(^d)(NSString *)=self.done;if(!d)return;
 self.done=nil;if(openEntry==self)openEntry=nil;
 UIAlertController *a=self.alert;   /* still up when Return, a test or a refused presentation answered */
 if(a.presentingViewController&&![a isBeingDismissed])[a.presentingViewController dismissViewControllerAnimated:YES completion:nil];
 runtime_input_clear();   /* what a controller pressed while the box was open */
 fprintf(stderr,"[totk] keyboard: text entry box %s\n",text?"confirmed":"cancelled");
 d(text);
}
@end
/* Diagnostics (TOTK_INPUT_FILE kbtype / kbenter / kbesc / kbshot, runtime/input.c) on the open box. Off the main thread a
   command first waits up to 5 s for a box to be on the screen, so a command file can say kbtest, kbtype, kbenter in a row
   (the box opens on the main thread after kbtest returns). */
void runtime_front_text_test(const char *op,const char *text){
 NSString *o=[NSString stringWithUTF8String:op?op:""]?:@"",*t=[NSString stringWithUTF8String:text?text:""]?:@"";
 if(![NSThread isMainThread])for(int i=0;i<100;i++){
  __block BOOL shown=NO;
  dispatch_sync(dispatch_get_main_queue(), ^{TOTKTextEntry *e=openEntry;shown=e.done&&e.alert.presentingViewController;});
  if(shown)break;
  usleep(50000);
 }
 dispatch_async(dispatch_get_main_queue(), ^{
  TOTKTextEntry *e=openEntry;if(!e.done){fprintf(stderr,"[totk] keyboard test: no text entry box is open\n");return;}
  if([o isEqualToString:@"type"]){UITextField *f=e.field;if(f)f.text=[(f.text?:@"") stringByAppendingString:t];else e.text=[[e current] stringByAppendingString:t];[e refilter];}
  else if([o isEqualToString:@"enter"])[e confirm];
  else if([o isEqualToString:@"shot"]){   /* the box as drawn (screenshots of the game picture do not include UIKit views) */
   UIView *v=e.alert.view;NSData *png=nil;
   if(v.window&&v.bounds.size.width>0&&v.bounds.size.height>0){
    UIGraphicsImageRenderer *r=[[UIGraphicsImageRenderer alloc] initWithSize:v.bounds.size];
    png=[r PNGDataWithActions:^(UIGraphicsImageRendererContext *c){(void)c;[v drawViewHierarchyInRect:(CGRect){CGPointZero,v.bounds.size} afterScreenUpdates:YES];}];
   }
   BOOL ok=[png writeToFile:t atomically:YES];
   fprintf(stderr,"[totk] keyboard test: box picture %s %s\n",t.UTF8String,ok?"written":"FAILED");return;}
  else if([o isEqualToString:@"esc"])[e finish:nil];
  fprintf(stderr,"[totk] keyboard test: %s -> field \"%s\"\n",o.UTF8String,[e current].UTF8String);
 });
}
int runtime_front_text_input(const RuntimeTextRequest *req,char *out,size_t out_size){
 if(!req||!out||!out_size){fprintf(stderr,"[totk] keyboard: no text entry request; cancelled\n");return 0;}
 if(!text_entry_enabled()){fprintf(stderr,"[totk] keyboard: text entry box off (TOTK_IOS_TEXT_ENTRY=0); cancelled\n");return 0;}
 /* The caller waits for the main thread to show the box, so a call on the main thread itself is cancelled at once (the
    game calls from its own threads). */
 if([NSThread isMainThread]){fprintf(stderr,"[totk] keyboard: text entry asked for on the main thread; cancelled\n");return 0;}
 int confirmed=0;
 @autoreleasepool{
  NSString *title=[NSString stringWithUTF8String:req->title?req->title:req->prompt?req->prompt:""]?:@"";
  NSString *detail=[NSString stringWithUTF8String:req->detail?req->detail:""]?:@"",*initial=[NSString stringWithUTF8String:req->initial?req->initial:""]?:@"";
  int maxU=req->max_units,minU=req->min_units,digits=req->digits_only,secure=req->secure;uint32_t dis=req->disabled;
  __block NSString *result=nil;dispatch_semaphore_t sem=dispatch_semaphore_create(0);
  dispatch_async(dispatch_get_main_queue(), ^{
   TOTKTextEntry *entry=[TOTKTextEntry new];
   entry.heading=title;entry.detail=detail;entry.text=initial;
   entry.maxUnits=maxU;entry.minUnits=minU;entry.digitsOnly=digits;entry.secure=secure;entry.disabled=dis;
   entry.done=^(NSString *text){result=[text copy];dispatch_semaphore_signal(sem);};
   openEntry=entry;
   runtime_input_clear();   /* nothing stays held while the player types */
   [entry show];
  });
  dispatch_semaphore_wait(sem,DISPATCH_TIME_FOREVER);
  if(result){snprintf(out,out_size,"%s",result.UTF8String?:"");confirmed=1;}
 }
 return confirmed;
}
static int viReady;
static unsigned displayIdentity,layerIdentity;
static void vi_initialize(void){if(!metalLayer)runtime_fail("VI requires the native iOS view");viReady=1;fprintf(stderr,"[totk] native VI display initialized\n");}
static uint32_t vi_open(void **out){if(!viReady||!out)return 0xf601;*out=&displayIdentity;return 0;}
static uint32_t vi_layer(void **out,void *display){if(!out||display!=&displayIdentity)return 0xf601;*out=&layerIdentity;return 0;}
static uint32_t vi_window(void **out,void *layer){if(!out||layer!=&layerIdentity)return 0xf601;*out=front_metal_layer();return 0;}
static uint32_t vi_vsync(void *ev,void *display){
 if(!ev||display!=&displayIdentity)return 0xf601;hle_bind_system_event(ev,1);
 pthread_mutex_lock(&vsyncLock);if(vsyncCount>=16)runtime_fail("VI display event limit");vsyncEvents[vsyncCount++]=ev;pthread_mutex_unlock(&vsyncLock);return 0;
}
void *runtime_front_override(const char *name){
 static const struct{const char *name;void *fn;} entries[]={
 {"_ZN2nn2vi10InitializeEv",vi_initialize},{"_ZN2nn2vi18OpenDefaultDisplayEPPNS0_7DisplayE",vi_open},
 {"_ZN2nn2vi11CreateLayerEPPNS0_5LayerEPNS0_7DisplayE",vi_layer},{"_ZN2nn2vi15GetNativeWindowEPPvPNS0_5LayerE",vi_window},
 {"_ZN2nn2vi20GetDisplayVsyncEventEPNS_2os15SystemEventTypeEPNS0_7DisplayE",vi_vsync}};
 for(unsigned i=0;i<sizeof(entries)/sizeof(*entries);i++)if(!strcmp(name,entries[i].name))return entries[i].fn;return NULL;
}
