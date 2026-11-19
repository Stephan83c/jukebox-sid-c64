/* Mini console (remplace conio) : texte directement en RAM écran, couleurs en RAM couleur. */
#define COLOR_BLACK 0
#define COLOR_WHITE 1
#define COLOR_YELLOW 7
#define COLOR_LIGHTRED 10
#define COLOR_GRAY2 12
#define COLOR_LIGHTGREEN 13
#define COLOR_LIGHTBLUE 14

static unsigned char cx, cy, col = COLOR_WHITE;
#define SCR ((volatile unsigned char *)0x0400)
#define COL ((volatile unsigned char *)0xD800)

static void gotoxy(unsigned char x, unsigned char y) { cx = x; cy = y; }
static void cputc(unsigned char c)
{
    unsigned o = cy * 40u + cx;
    if (c >= 96 && c < 128) { c -= 32; }   /* minuscules -> majuscules */
    SCR[o] = c & 0x3F;          /* ASCII 32-95 -> code écran */
    COL[o] = col;
    if (++cx >= 40) { cx = 0; if (cy < 24) ++cy; }
}
static void cputs(const char *s) { while (*s) cputc(*s++); }
static void textcolor(unsigned char c) { col = c; }
static void bordercolor(unsigned char c) { *(volatile unsigned char *)0xD020 = c; }
static void bgcolor(unsigned char c) { *(volatile unsigned char *)0xD021 = c; }
static void clrscr(void)
{
    unsigned i;
    for (i = 0; i < 1000; ++i) { SCR[i] = 32; }
    cx = cy = 0;
}
static void cursor(unsigned char on) { (void)on; }
static unsigned char cgetc(void)
{
    unsigned char k;
    do {
        k = __asm { jsr 0xffe4 ; sta accu ; lda #0 ; sta accu + 1 };
    } while (!k);
    return k;
}
