#!/usr/bin/env python
# coding: utf-8

"""
    Dragon 32 Character Map Information
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    :copyleft: 2013 by Jens Diemer
    :license: GNU GPL v3 or above

    arrows: http://www.pylucid.org/de/contribute/developer-documentation/unicode-test/decode_unicode/arrows/#8593
    blocks: http://www.pylucid.org/de/contribute/developer-documentation/unicode-test/decode_unicode/block-elements/#9600
"""

INVERTED = "INVERTED"
NORMAL = "NORMAL"
GREEN = "GREEN"
YELLOW = "YELLOW"
BLUE = "BLUE"
RED = "RED"
WHITE = "WHITE"
CYAN ="CYAN"
MAGENTA = "MAGENTA"
ORANGE ="ORANGE"

COLORS = (GREEN,YELLOW,BLUE,RED,WHITE,CYAN,MAGENTA,ORANGE)

COLOR_INFO = {
    GREEN: (0,255,0), # XRoar: 08ff08
    YELLOW: (255,255,0), # XRoar: ffff42
    BLUE: (0,0,180), # XRoar: 2110b5
    RED: (180,0,0), # XRoar: b50421
    WHITE: (255,255,255), # XRoar: ffffff
    CYAN: (0,255,255), # XRoar: 08d773
    MAGENTA: (255,0,255), # XRoar: ff1cff
    ORANGE: (255,128,0), # XRoar: ff4108
}

def get_rgb_color(color):
    if color == INVERTED:
        foreground=(0,255,0)
        background=(0,65,0)
    elif color == NORMAL:
        foreground=(0,65,0)
        background=(0,255,0)
    else:
        foreground=(0,0,0)
        background=COLOR_INFO[color]
    return (foreground, background)

DRAGON_CHARS_MAP = []

chars_map = [
    (0, 64, '@', INVERTED),
    (1, 65, 'A', INVERTED),
    (2, 66, 'B', INVERTED),
    (3, 67, 'C', INVERTED),
    (4, 68, 'D', INVERTED),
    (5, 69, 'E', INVERTED),
    (6, 70, 'F', INVERTED),
    (7, 71, 'G', INVERTED),
    (8, 72, 'H', INVERTED),
    (9, 73, 'I', INVERTED),
    (10, 74, 'J', INVERTED),
    (11, 75, 'K', INVERTED),
    (12, 76, 'L', INVERTED),
    (13, 77, 'M', INVERTED),
    (14, 78, 'N', INVERTED),
    (15, 79, 'O', INVERTED),
    (16, 80, 'P', INVERTED),
    (17, 81, 'Q', INVERTED),
    (18, 82, 'R', INVERTED),
    (19, 83, 'S', INVERTED),
    (20, 84, 'T', INVERTED),
    (21, 85, 'U', INVERTED),
    (22, 86, 'V', INVERTED),
    (23, 87, 'W', INVERTED),
    (24, 88, 'X', INVERTED),
    (25, 89, 'Y', INVERTED),
    (26, 90, 'Z', INVERTED),
    (27, 91, '[', INVERTED),
    (28, 92, '\\', INVERTED),
    (29, 93, ']', INVERTED),

    (30, 2191, u'\N{UPWARDS ARROW}', INVERTED),
    (31, 2190, u'\N{LEFTWARDS ARROW}', INVERTED),

    (32, 32, ' ', INVERTED),
    (33, 33, '!', INVERTED),
    (34, 34, '"', INVERTED),
    (35, 35, '#', INVERTED),
    (36, 36, '$', INVERTED),
    (37, 37, '%', INVERTED),
    (38, 38, '&', INVERTED),
    (39, 39, "'", INVERTED),
    (40, 40, '(', INVERTED),
    (41, 41, ')', INVERTED),
    (42, 42, '*', INVERTED),
    (43, 43, '+', INVERTED),
    (44, 44, ',', INVERTED),
    (45, 45, '-', INVERTED),
    (46, 46, '.', INVERTED),
    (47, 47, '/', INVERTED),
    (48, 48, '0', INVERTED),
    (49, 49, '1', INVERTED),
    (50, 50, '2', INVERTED),
    (51, 51, '3', INVERTED),
    (52, 52, '4', INVERTED),
    (53, 53, '5', INVERTED),
    (54, 54, '6', INVERTED),
    (55, 55, '7', INVERTED),
    (56, 56, '8', INVERTED),
    (57, 57, '9', INVERTED),
    (58, 58, ':', INVERTED),
    (59, 59, ';', INVERTED),
    (60, 60, '<', INVERTED),
    (61, 61, '=', INVERTED),
    (62, 62, '>', INVERTED),
    (63, 63, '?', INVERTED),
]

CHARS = (
    u"@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\]"
    u"\N{UPWARDS ARROW}"
    u"\N{LEFTWARDS ARROW}"
    u" !\"#$%&'()*+,-./0123456789:;<=>?"
)

# Add CHARS
for item_type in (INVERTED, NORMAL):
    for item in CHARS:
        codepoint = ord(item)
        DRAGON_CHARS_MAP.append(
            (item, item_type)
        )


BLOCKS=(
    u'\N{FULL BLOCK}' # XXX: complete black
    u'\N{QUADRANT UPPER LEFT AND UPPER RIGHT AND LOWER LEFT}'
    u'\N{QUADRANT UPPER LEFT AND UPPER RIGHT AND LOWER RIGHT}'
    u'\N{UPPER HALF BLOCK}'
    u'\N{QUADRANT UPPER LEFT AND LOWER LEFT AND LOWER RIGHT}'
    u'\N{LEFT HALF BLOCK}'
    u'\N{QUADRANT UPPER LEFT AND LOWER RIGHT}'
    u'\N{QUADRANT UPPER LEFT}'
    u'\N{QUADRANT UPPER RIGHT AND LOWER LEFT AND LOWER RIGHT}'
    u'\N{QUADRANT UPPER RIGHT AND LOWER LEFT}'
    u'\N{RIGHT HALF BLOCK}'
    u'\N{QUADRANT UPPER RIGHT}'
    u'\N{LOWER HALF BLOCK}'
    u'\N{QUADRANT LOWER LEFT}'
    u'\N{QUADRANT LOWER RIGHT}'
    u' ' # XXX: complete filled with color
)

# Add BLOCKS in every color to chars_map
for item_type in COLORS:
    for item in BLOCKS:
        DRAGON_CHARS_MAP.append(
            (item, item_type)
        )


def list_chars():
    index = 0
    for x in xrange(8):
        line = u""
        for y in xrange(32):
            try:
                line += DRAGON_CHARS_MAP[index][0]
            except KeyError:
                break
            index +=1
        print line.encode("utf-8")


def create_wiki_page():
    """
    for http://archive.worldofdragon.org/index.php?title=CharMap
    """
    print (
        '{| class="wikitable"'
        ' style="font-family: monospace;'
        ' background-color:#ffffcc;"'
        ' cellpadding="10"'
    )
    print "|-"
    print "! POKE"
    print "value"
    print "! "
    print "! unicode"
    print "codepoint"
    print "! type"
    print "|-"
    for no, data in enumerate(DRAGON_CHARS_MAP):
        item, item_type = data

        codepoint = ord(item)
        print u"|%i" % no

        foreground, background=get_rgb_color(item_type)
        foreground="#%02x%02x%02x" % foreground
        background="#%02x%02x%02x" % background

        style="color: #%s;"
        print '| style="color:%s; background-color:%s;" | &#x%x;' % (
            foreground, background, codepoint
        )
        print "|%i" % codepoint
        print "|%s" % item_type
        print "|-"
    print "|}"


if __name__ == "__main__":
    create_wiki_page()