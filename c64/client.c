/* SID Jukebox, client C64 : partie C, compilée avec Oscar64 (voir build.sh).
 *
 * Le lecteur (play.s, logo.s, scroll.s) est assemblé à part avec ca65/ld65 (asm.bin) et placé en tête de la zone
 * résidente (adresse RUN = HISTART) ; il n'utilise aucun octet de page zéro. Le programme est chargé en $0801 ; le
 * petit copieur de la section rcode (main, ci-dessous) recopie l'image de $0900 vers RUN, remet la ROM du BASIC
 * hors circuit ($01 = $36, la zone $A000-$BFFF devient de la RAM) puis appelle jukebox() (main.c).
 * Mémoire : tout le reste de $0800 à RUN-1 est libre pour le morceau reçu ; la pile d'Oscar64 est en haut de la
 * zone résidente (jusqu'à $D000). Pas de conio : console.c écrit directement dans la RAM écran.
 */
#include <string.h>

#define LF 10
#ifdef DEMO
#include "demo.h"
#endif
#include "asmsyms.h"   /* généré par build.sh : adresses des variables et de play_run dans asm.bin */
#include "uci.h"

#pragma stacksize(256)
#pragma heapsize(0)

#pragma section(startup, 0)
#pragma region(startup, 0x0801, 0x0870, , , { startup })
#pragma section(rcode, 0)
#pragma region(rcode, 0x0870, 0x0900, , , { rcode })
#pragma section(asmsec, 0)
#pragma region(main, 0x0900, 0x0900 + 0xD000 - RUN, , , { asmsec, code, data, bss, heap, stack }, RUN)

#pragma data(asmsec)
__export unsigned char asmblob[ASMSIZE] = {
#embed "build/asm.bin"
};
#pragma data(data)

static unsigned char play_run(void)
{
    return __asm { jsr PLAY_RUN_ADDR ; sta accu ; lda #0 ; sta accu + 1 };
}

#include "console.c"
#include "uci.c"
#include "main.c"

#pragma code(rcode)
int main(void)
{
    __asm volatile {
        sei
        lda #<0x0900
        sta 0xfb
        lda #>0x0900
        sta 0xfc
        lda #<RUN
        sta 0xfd
        lda #>RUN
        sta 0xfe
        ldx #>(IMGEND - 0x0900)
        beq .part
        ldy #0
    .cp:
        lda (0xfb),y
        sta (0xfd),y
        iny
        bne .cp
        inc 0xfc
        inc 0xfe
        dex
        bne .cp
    .part:
        ldy #0
        cpy #<(IMGEND - 0x0900)
        beq .fin
    .cq:
        lda (0xfb),y
        sta (0xfd),y
        iny
        cpy #<(IMGEND - 0x0900)
        bne .cq
    .fin:
        lda #0x36
        sta 0x01
        cli
    }
    jukebox();
    return 0;
}
