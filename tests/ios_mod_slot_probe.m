/* The real choice of the player mod folder (main.m apply_player_mods), without the UIKit front end. It takes the plain
   mods folder as its argument and prints what the runtime would be handed; the function itself logs to stderr. No game
   content or device connection. */
#import <Foundation/Foundation.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include PRODUCTION_CHOICE

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    @autoreleasepool {
        apply_player_mods(@(argv[1]));
    }
    const char *mods = getenv("TOTK_ROMFS_MODS");
    printf("%s\n", mods ? mods : "(not set)");
    return 0;
}
