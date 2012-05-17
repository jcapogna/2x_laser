#!/usr/bin/env python

import os, sys, time, glob
from math import ceil, floor
from subprocess import *
from itertools import *
from PIL import Image
from raster_gui import *


if ( len(sys.argv) > 1 and os.path.exists(sys.argv[1]) ):
    image_name = sys.argv[1]
else:
    image_name = image_not_found()

print('%')
print '(image = %s)' % image_name

image = Image.open(image_name)

(img_w,img_h) = image.size
print('(original size w=%u,h=%u)' % (img_w,img_h))

# user defined parameters
SPEED = 600
ACCEL = 300
laser_power = 0.15
laser_on_time = 0.5
is_metric = 0
origin_x = 0
origin_y = 0
# center, <top|middle|bottom><left|center|right>
origin_loc = 'topleft'
# for mirroring
orientation_y = -1
orientation_x = 1
raster_w = 3
raster_h = raster_w*float(img_h)/img_w
XDPI = 200
YDPI = 200

# calc lead in + 100% fudge
leadIn = (1.0*SPEED*SPEED/3600)/ACCEL
#leadIn = 1

# calc image raster size
pix_w = int(raster_w * XDPI)
pix_h = int(raster_h * YDPI)
W = float(pix_w) / XDPI
H = float(pix_h) / YDPI
MAX_BPF = 53

# handle origin offsetting
if ( origin_loc == 'center' ):
    X = origin_x - W/2.0
    Y = origin_y + H/2.0
else:
    if ( 'top' in origin_loc ):
        Y = origin_y
    elif ( 'bottom' in origin_loc ):
        Y = origin_y + H
    elif ( 'middle' in origin_loc ):
        Y = origin_y + H/2.0
    else:
        print('unknown origin_loc='+origin_loc)
        sys.exit()

    if ( 'left' in origin_loc ):
        X = origin_x
    elif ( 'center' in origin_loc ):
        X = origin_x - W/2.0
    elif ( 'right' in origin_loc ):
        X = origin_x - W
    else:
        print('unknown origin_loc='+origin_loc)
        sys.exit()

print '(rescaling to %u,%u w=%u,h=%u)' % (pix_w, pix_h, W, H)
image = image.resize((pix_w, pix_h), Image.BICUBIC).convert('1')
image.save('actual.png')

pix = list(image.getdata())

# gcode header
if ( is_metric ):
    print('G21')
else:
    print('G20')
print('M63 P0 (turn off laser dout)')
print('G0 Z0 (turn off magic z)')
print('G64 P0.0001 Q0.0001 (minimal path blending)')
print('M68 E0 Q%0.3f (set laser power level)' % laser_power)
print('M3 S1 (master laser power on)')
print('#<raster_speed> = %0.3f' % SPEED)

# gcode skip lines that show raster image run box
print('/ F[#<raster_speed>]')
print('/ G0 X%0.3f Y%0.3f' % (X,Y))
print('/ G1 X%0.3f Y%0.3f' % (X+W*orientation_x,Y))
print('/ G1 X%0.3f Y%0.3f' % (X+W*orientation_x,Y+H*orientation_y))
print('/ G1 X%0.3f Y%0.3f' % (X,Y+H*orientation_y))
print('/ G1 X%0.3f Y%0.3f' % (X,Y))
print('/ M2')

forward = 1

for y in xrange(0,pix_h):
    offset_y = Y + float(y)/YDPI*orientation_y

    print('(setup raster line %d)' % y)

    row = pix[y * pix_w:(y + 1) * pix_w]

    if not forward:
        row.reverse()

    first_non_zero = -1
    last_non_zero = -1
    for index, pixel in enumerate(row):
        if (pixel <= 127):
            if (first_non_zero == -1):
                first_non_zero = index
            last_non_zero = index

    # debug raster
    #first_non_zero, last_non_zero = (0,len(row)-1)

    # some data to output
    if (first_non_zero >= 0):
        # figure out how many max bpf floats to hold the data and
        # then evenly distribute the bits
        total_bits = last_non_zero - first_non_zero + 1;
        BPF = ceil(total_bits / (ceil(float(total_bits) / MAX_BPF)))

        bits = []
        i=0
        bitval=0
        for v in row[first_non_zero:last_non_zero+1]:
            if (v <= 127):
                bitval += (1<<i)
            i += 1
            if (i >= BPF):
                bits.append(bitval);
                bitval = 0
                i = 0
        if (i > 0):
            bits.append(bitval);

	if forward:
            offset_start = X + (float(first_non_zero)/XDPI - leadIn)*orientation_x
            offset_end = X + (float(last_non_zero+1)/XDPI + leadIn)*orientation_x
        else:
            offset_start = X + (W - float(first_non_zero)/XDPI + leadIn)*orientation_x
            offset_end = X + (W - float(last_non_zero+1)/XDPI - leadIn)*orientation_x

        print('G0 X%0.3f Y%0.3f' % (offset_start,offset_y))
        print('F[#<raster_speed>]')
        print('M68 E1 Q-1 (start new line)')
        print('M68 E2 Q%d (gcode is metric 0=no,1=yes)' % is_metric)
        print('M68 E1 Q-2')
        print('M68 E2 Q[#<raster_speed>] (speed, in/min or mm/min)')
        print('M68 E1 Q-3')
        print('M68 E2 Q%d (direction)' % (1 if forward else -1))
        print('M68 E1 Q-4')
        print('M68 E2 Q%0.3f (dpi)' % XDPI)
        print('M68 E1 Q-5')
        print('M68 E2 Q%u (bits per float)' % BPF)
        print('M68 E1 Q-6')
        print('M68 E2 Q%d (laser on time, ns)' % (laser_on_time*1000000))
        print('M68 E1 Q-7')
        print('M68 E2 Q%0.3f (lead in)' % leadIn)
        print('M68 E1 Q-8')
        print('(raster data start)')

        for index, bitval in enumerate(bits):
            if forward:
                offset_i = X + float(first_non_zero + index*BPF)/XDPI*orientation_x
            else:
                offset_i = X + (W - float(first_non_zero + index*BPF)/XDPI)*orientation_x
            print('M68 E2 Q%u' % (bitval))
            print('M68 E1 Q%u' % (index+1))
            #print('G1 X%0.3f' % offset_i)

        print('G1 X%0.3f' % offset_end)
        print('M1')

    # next line is reverse direction
    forward = not forward


print('%')
