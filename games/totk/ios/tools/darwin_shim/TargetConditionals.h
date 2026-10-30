/* Apple's TargetConditionals.h for a build without Apple's SDK (ios/tools/export_ios_windows.py): the build passes
   -DTARGET_OS_IPHONE=0 for the Mac's patch path, which the iOS export runs, or 1 for the device's checks. */
#pragma once
#ifndef TARGET_OS_IPHONE
#error "export_ios_windows.py passes -DTARGET_OS_IPHONE=0 or 1"
#endif
#define TARGET_OS_OSX (!TARGET_OS_IPHONE)
