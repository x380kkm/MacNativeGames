/* What production nvn_refl_from_json says of a fragment function's colour outputs. argv[1]: a reflection as JSON; prints
   colors_listed and color_outputs. No game content or device connection. */
#import "nvn_refl.h"
#include <stdio.h>

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    @autoreleasepool {
        nvn_refl reflection;
        char error[160];
        NSData *json = [@(argv[1]) dataUsingEncoding:NSUTF8StringEncoding];
        if (nvn_refl_from_json([NSJSONSerialization JSONObjectWithData:json options:0 error:nil], &reflection, error, sizeof error)) {
            printf("refused: %s\n", error);
            return 1;
        }
        printf("%d %d\n", reflection.colors_listed, reflection.color_outputs);
    }
    return 0;
}
