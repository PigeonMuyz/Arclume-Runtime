#import <AppKit/AppKit.h>
#import "cocoa_icon_utils.h"
#include <assert.h>

static NSImage *fixture(size_t width, size_t height, CGRect content)
{
    CGColorSpaceRef space = CGColorSpaceCreateDeviceRGB();
    CGContextRef ctx = CGBitmapContextCreate(NULL, width, height, 8, width * 4, space, (CGBitmapInfo)kCGImageAlphaPremultipliedLast);
    CGColorSpaceRelease(space);
    CGContextSetRGBFillColor(ctx, 1, 0.6, 0, 1);
    CGContextFillRect(ctx, content);
    CGImageRef cg = CGBitmapContextCreateImage(ctx);
    NSImage *image = [[[NSImage alloc] initWithCGImage:cg size:NSMakeSize(width, height)] autorelease];
    CGImageRelease(cg);
    CGContextRelease(ctx);
    return image;
}

static CGRect bounds(NSImage *image)
{
    CGRect proposed = {CGPointZero, image.size};
    CGImageRef cg = [image CGImageForProposedRect:&proposed context:nil hints:nil];
    CGColorSpaceRef space = CGColorSpaceCreateDeviceRGB();
    CGContextRef ctx = CGBitmapContextCreate(NULL, 512, 512, 8, 2048, space, (CGBitmapInfo)kCGImageAlphaPremultipliedLast);
    CGColorSpaceRelease(space);
    CGContextDrawImage(ctx, CGRectMake(0, 0, 512, 512), cg);
    const unsigned char *data = CGBitmapContextGetData(ctx);
    int minX = 512, minY = 512, maxX = -1, maxY = -1;
    for (int y = 0; y < 512; ++y)
        for (int x = 0; x < 512; ++x)
            if (data[(y * 512 + x) * 4 + 3] > 24) {
                minX = MIN(minX, x); minY = MIN(minY, y);
                maxX = MAX(maxX, x); maxY = MAX(maxY, y);
            }
    CGContextRelease(ctx);
    return CGRectMake(minX, minY, maxX - minX + 1, maxY - minY + 1);
}

int main(void)
{
    @autoreleasepool {
        assert([WineIconUtils dockIconFromImage:nil] == nil);
        NSImage *empty = fixture(512, 512, CGRectZero);
        assert([WineIconUtils dockIconFromImage:empty] == empty);
        CGRect square = bounds([WineIconUtils dockIconFromImage:fixture(512, 512, CGRectMake(0, 0, 512, 512))]);
        assert(square.size.width >= 408 && square.size.width <= 412);
        assert(fabs(square.size.width - square.size.height) < 2);
        assert(fabs(CGRectGetMidX(square) - 256) < 2);
        CGRect wide = bounds([WineIconUtils dockIconFromImage:fixture(512, 256, CGRectMake(0, 0, 512, 256))]);
        assert(fabs(wide.size.width / wide.size.height - 2) < 0.02);
        CGRect tall = bounds([WineIconUtils dockIconFromImage:fixture(256, 512, CGRectMake(0, 0, 256, 512))]);
        assert(fabs(tall.size.height / tall.size.width - 2) < 0.02);
        CGRect padded = bounds([WineIconUtils dockIconFromImage:fixture(512, 512, CGRectMake(80, 80, 352, 352))]);
        assert(fabs(padded.size.width - 352) < 2);
        puts("PASS: nil, transparent, square, landscape, portrait, already-padded Dock icons");
    }
    return 0;
}
