; Lecteur de SID (PSID, cadence = une image) avec visualisation, pour le C64.
;
; unsigned char play_run(void) : initialise le morceau (init_addr, sous-morceau song_nr),
; puis appelle play_addr à chaque image (interruption raster) pendant frames_max images.
;
; Pendant la lecture la page zéro appartient au morceau : elle est sauvegardée avant et
; restaurée après, et ce code n'en utilise aucun octet. Le clavier est lu directement
; (le KERNAL ne tourne pas).
;
; Visualisation (vis_on = 1) : les registres du SID sont en écriture seule. Pendant l'appel
; du morceau, $D000-$DFFF est donc mis en RAM ($01 = $34) : ses écritures vers $D400-$D418
; tombent dans la RAM, on en garde une copie ("shadow"), puis on la recopie vers le vrai SID.
; À partir de cette copie on simule l'enveloppe de chaque voix (vu-mètres) et on place
; barre horizontale par voix (vu-mètres).
;
; Retour : 0 fin de durée, 1 ESPACE (suivant), 2 Q (quitter), 3 S (recherche),
;          4 C (effacer le filtre), 5 V (effets on/off, morceau suivant).
; Chaque seconde, le temps écoulé est écrit à l'écran (ligne 7, colonne 6).
;
; Scroller de démo : une ligne de texte défile en douceur (scroll matériel $D016, limité à cette
; ligne par deux interruptions raster : une avant, une après) ; les couleurs tournent.
;
; Thème : écran de lecture noir en banque VIC 3 avec jeu de caractères personnalisé (traits fins
; des vu-mètres, logo géant dont les couleurs défilent).

        .macpack cbm
        .export _play_run, _init_addr, _play_addr, _frames_max, _song_nr, _fps, _vis_on
        .import logo_glyphs, logo_row0, logo_row1, scr_glyphs, scrtext


TIME_OFS   = 9 * 40 + 6             ; position du temps écoulé (ligne 9, colonne 6)
LOGO_ROW   = 0                      ; le logo occupe les lignes 0 et 1
LOGO_COL   = 9                      ; première colonne du logo (11 lettres x 2 colonnes)
LOGO_LEN   = 320                    ; octets de formes du logo (10 lettres x 4 caractères x 8)
RASTER     = 252                    ; ligne raster où le morceau est appelé (bas d'écran)
SCROLL_ROW = 19                     ; scroller : lettres de 12 pixels de haut sur les lignes 19 et 20
SCRL       = SCR2 + SCROLL_ROW * 40
LINE_A     = 50 + 8 * SCROLL_ROW    ; juste avant la ligne : on décale l'affichage
LINE_B     = 58 + 8 * (SCROLL_ROW + 1)   ; dernière ligne du scroller : on remet le décalage à 0
SPEED      = 2                      ; pixels par image
SCR2       = $F400                  ; écran de lecture avec effets (RAM sous le KERNAL, banque VIC 3)
CHR2       = $F800                  ; jeu de caractères de lecture

        .bss
_init_addr:  .res 2
_play_addr:  .res 2
_frames_max: .res 2
_song_nr:    .res 1
_fps:        .res 1
_vis_on:     .res 1
next:        .res 2
digits:      .res 4         ; minutes dizaines/unités, secondes dizaines/unités
frames:      .res 2
seen:        .res 1
result:      .res 1
zpsave:      .res 256
shadow:      .res 25        ; copie des registres $D400-$D418
prevg:       .res 3         ; gate précédent de chaque voix
state:       .res 3         ; 0 relâchement, 1 attaque, 2 déclin/maintien
level:       .res 3         ; niveau d'enveloppe simulé 0-255
vh:          .res 3         ; longueur de barre 0-255 (pixels)
vi:          .res 1
vo:          .res 1
tmp:         .res 1
tmp2:        .res 1
xs:          .res 1         ; décalage fin du scroller (0-7)
stage:       .res 1         ; 0 = avant le scroller, 1 = après, 2 = le morceau
tpos:        .res 2         ; prochain caractère du texte
sbuf:        .res 40        ; texte visible du scroller, ligne du haut (la RAM sous le KERNAL ne peut pas être relue)
sbufb:       .res 40        ; ligne du bas
nbot:        .res 1         ; code de la case du bas du caractère suivant

        .rodata
; pas par image (20 ms) : attaque (2 ms .. 8 s) puis déclin/relâchement (6 ms .. 24 s)
astep:  .byte 255, 255, 255, 212, 134, 91, 75, 64, 51, 20, 10, 6, 5, 2, 1, 1
dstep:  .byte 255, 212, 106, 71, 45, 30, 25, 21, 17, 7, 3, 2, 2, 1, 1, 1
; traits de 0 à 8 pixels de large, 2 pixels de haut (lignes 3 et 4 de la case)
glyphs: .byte 0,0,0,$00,$00,0,0,0
        .byte 0,0,0,$80,$80,0,0,0
        .byte 0,0,0,$C0,$C0,0,0,0
        .byte 0,0,0,$E0,$E0,0,0,0
        .byte 0,0,0,$F0,$F0,0,0,0
        .byte 0,0,0,$F8,$F8,0,0,0
        .byte 0,0,0,$FC,$FC,0,0,0
        .byte 0,0,0,$FE,$FE,0,0,0
        .byte 0,0,0,$FF,$FF,0,0,0

; couleurs du logo et du scroller (défilent)
rainbow: .byte 2, 8, 7, 5, 3, 14, 4, 10
; Dégradé arc-en-ciel des vu-mètres, une couleur par case (32 cases), sans noir.
vucolors:
        .byte   2, 2, 2, 2, 8, 8, 8, 8
        .byte   7, 7, 7, 13, 13, 13, 13, 5
        .byte   5, 5, 3, 3, 3, 3, 14, 14
        .byte   14, 6, 6, 6, 6, 4, 4, 4

        .code

; Lit le clavier : A = 0 rien, 1 ESPACE, 2 Q, 3 S, 4 C, 5 V.
keys:
        lda     #$7F            ; colonne 7 : ESPACE (ligne 4), Q (ligne 6)
        sta     $DC00
        lda     $DC01
        tax
        and     #$10
        beq     @space
        txa
        and     #$40
        beq     @q
        lda     #$FD            ; colonne 1 : S (ligne 5)
        sta     $DC00
        lda     $DC01
        and     #$20
        beq     @s
        lda     #$FB            ; colonne 2 : C (ligne 4)
        sta     $DC00
        lda     $DC01
        and     #$10
        beq     @c
        lda     #$F7            ; colonne 3 : V (ligne 7)
        sta     $DC00
        lda     $DC01
        and     #$80
        beq     @v
        lda     #0
        rts
@space: lda     #1
        rts
@q:     lda     #2
        rts
@s:     lda     #3
        rts
@c:     lda     #4
        rts
@v:     lda     #5
        rts

; Ajoute une seconde au temps écoulé et le réécrit à l'écran.
tick:
        clc
        lda     next
        adc     _fps
        sta     next
        bcc     @a
        inc     next + 1
@a:     inc     digits + 3
        lda     digits + 3
        cmp     #10
        bcc     @draw
        lda     #0
        sta     digits + 3
        inc     digits + 2
        lda     digits + 2
        cmp     #6
        bcc     @draw
        lda     #0
        sta     digits + 2
        inc     digits + 1
        lda     digits + 1
        cmp     #10
        bcc     @draw
        lda     #0
        sta     digits + 1
        inc     digits
@draw:  lda     digits
        ora     #$30
        sta     SCR2 + TIME_OFS
        lda     digits + 1
        ora     #$30
        sta     SCR2 + TIME_OFS + 1
        lda     digits + 2
        ora     #$30
        sta     SCR2 + TIME_OFS + 3
        lda     digits + 3
        ora     #$30
        sta     SCR2 + TIME_OFS + 4
        rts

silence:
        ldx     #$18
        lda     #0
@l:     sta     $D400,x
        dex
        bpl     @l
        rts

; Copie la RAM $D400-$D418 (ce que le morceau vient d'écrire) dans "shadow", remet les
; E/S en place ($01 = $36) et recopie "shadow" vers le vrai SID.
sync_sid:
        ldx     #24
@cp:    lda     $D400,x
        sta     shadow,x
        dex
        bpl     @cp
        lda     #$36
        sta     $01
        ldx     #0
@wr:    lda     shadow,x
        sta     $D400,x
        inx
        cpx     #25
        bne     @wr
        rts

; ---------------------------------------------------------------- effets

; Met à jour l'enveloppe simulée, les vu-mètres et l'analyseur à partir de "shadow".
model:
        lda     #0
        sta     vi
        sta     vo
@voice: ldy     vi
        ldx     vo
        lda     shadow + 4,x    ; contrôle : bit 0 = gate
        and     #1
        sta     tmp
        cmp     prevg,y
        beq     @gdone
        sta     prevg,y
        lda     tmp
        beq     @grel
        lda     #1              ; gate monte : attaque
        sta     state,y
        bne     @gdone
@grel:  lda     #0              ; gate descend : relâchement
        sta     state,y
@gdone: lda     state,y
        beq     @release
        cmp     #1
        beq     @attack
        ; --- déclin vers le niveau de maintien
        lda     shadow + 6,x
        lsr
        lsr
        lsr
        lsr
        sta     tmp
        asl
        asl
        asl
        asl
        ora     tmp
        sta     tmp2            ; niveau de maintien 0-255
        lda     level,y
        cmp     tmp2
        beq     @levdone
        bcc     @setsus         ; en dessous du maintien
        lda     shadow + 5,x
        and     #$0F
        tax
        lda     level,y
        sec
        sbc     dstep,x
        bcc     @setsus
        cmp     tmp2
        bcs     @store
@setsus: lda    tmp2
@store: sta     level,y
        jmp     @levdone
@attack:
        lda     shadow + 5,x
        lsr
        lsr
        lsr
        lsr
        tax
        lda     level,y
        clc
        adc     astep,x
        bcc     @astore
        lda     #255            ; sommet atteint : déclin
        sta     level,y
        lda     #2
        sta     state,y
        jmp     @levdone
@astore: sta    level,y
        jmp     @levdone
@release:
        lda     shadow + 6,x
        and     #$0F
        tax
        lda     level,y
        sec
        sbc     dstep,x
        bcs     @rstore
        lda     #0
@rstore: sta    level,y
@levdone:
        ; --- hauteur affichée : niveau / 8, 0 si aucune forme d'onde
        ldx     vo
        lda     shadow + 4,x
        and     #$F0
        bne     @wave
        lda     #0
        beq     @hset
@wave:  lda     level,y         ; longueur de barre en pixels (0-255)
@hset:  sta     vh,y
@nextv: lda     vo
        clc
        adc     #7
        sta     vo
        inc     vi
        lda     vi
        cmp     #3
        beq     @mend
        jmp     @voice
@mend:  rts

; Une barre fine (2 pixels de haut) : vh[vnum] pixels (0-255) sur 32 cases de 8 pixels.
; Caractères $E0-$E8 : trait de 0 à 8 pixels de large (voir "glyphs").
        .macro bar vnum, addr
        .local c, full, part, put
        ldy     #vnum
        lda     vh,y
        lsr
        lsr
        lsr
        sta     tmp             ; cases pleines
        lda     vh,y
        and     #7
        ora     #$E0
        sta     tmp2            ; case partielle
        ldx     #0
c:      cpx     tmp
        bcc     full
        beq     part
        lda     #$E0            ; vide
        bne     put
part:   lda     tmp2
        bne     put
full:   lda     #$E8            ; trait complet
put:    sta     addr,x
        inx
        cpx     #32
        bne     c
        .endmacro

; Colonne suivante du scroller : A = case du haut, nbot = case du bas. Le texte est un flux d'indices
; (0 = espace, n = n-ième lettre, $FF = fin, on recommence) ; la lettre n occupe les codes
; 64 + 2 * (n - 1) (haut) et le suivant (bas). N'utilise ni X ni Y.
next_char:
        lda     tpos
        sta     @rd + 1
        lda     tpos + 1
        sta     @rd + 2
@rd:    lda     a:$0000
        cmp     #$FF
        bne     @ok
        lda     #<scrtext
        sta     tpos
        lda     #>scrtext
        sta     tpos + 1
        jmp     next_char
@ok:    inc     tpos
        bne     @x
        inc     tpos + 1
@x:     cmp     #0
        bne     @gl
        lda     #32
        sta     nbot
        rts
@gl:    asl
        clc
        adc     #62
        sta     nbot
        inc     nbot
        rts

; Une image de scroller : décalage fin ; tous les 8 pixels, le texte glisse d'une colonne.
scroll_step:
        lda     xs
        sec
        sbc     #SPEED
        bcs     @store
        clc
        adc     #8
        pha
        ldx     #0
@sh:    lda     sbuf + 1,x
        sta     sbuf,x
        lda     sbufb + 1,x
        sta     sbufb,x
        inx
        cpx     #39
        bne     @sh
        jsr     next_char
        sta     sbuf + 39
        lda     nbot
        sta     sbufb + 39
        ldx     #39             ; recopie vers l'écran (en écriture seulement : sous la ROM)
@cp:    lda     sbuf,x
        sta     SCRL,x
        lda     sbufb,x
        sta     SCRL + 40,x
        dex
        bpl     @cp
        pla
@store: sta     xs
        ; couleurs des deux lignes : arc-en-ciel qui tourne
        lda     frames
        lsr
        sta     tmp
        ldx     #39
@co:    txa
        clc
        adc     tmp
        and     #7
        tay
        lda     rainbow,y
        sta     $D800 + SCROLL_ROW * 40,x
        sta     $D800 + SCROLL_ROW * 40 + 40,x
        dex
        bpl     @co
        rts

; Couleurs du logo : un arc-en-ciel qui défile (changement tous les 4 images).
logocolor:
        lda     frames
        lsr
        lsr
        sta     tmp
        ldx     #0
@l:     txa
        clc
        adc     tmp
        and     #7
        tay
        lda     rainbow,y
        sta     $D800 + LOGO_ROW * 40 + LOGO_COL,x
        sta     $D800 + (LOGO_ROW + 1) * 40 + LOGO_COL,x
        inx
        cpx     #22
        bne     @l
        rts

render:
        bar     0, SCR2 + 14 * 40 + 3
        bar     1, SCR2 + 15 * 40 + 3
        bar     2, SCR2 + 16 * 40 + 3
        rts

; Passage à l'écran de lecture : jeu de caractères (ROM recopiée + traits), copie de l'écran
; courant, banque VIC 3 ($C000-$FFFF), écran en $F400, caractères en $F800.
vis_start:
        lda     #$32            ; ROM des caractères visible en $D000 (pas de BASIC)
        sta     $01
        ldx     #0
@cc:    lda     $D000,x
        sta     CHR2,x
        lda     $D100,x
        sta     CHR2 + $100,x
        lda     $D200,x
        sta     CHR2 + $200,x
        lda     $D300,x
        sta     CHR2 + $300,x
        lda     $D400,x
        sta     CHR2 + $400,x
        lda     $D500,x
        sta     CHR2 + $500,x
        lda     $D600,x
        sta     CHR2 + $600,x
        lda     $D700,x
        sta     CHR2 + $700,x
        inx
        bne     @cc
        lda     #$36
        sta     $01
        ldx     #71             ; 9 traits : codes $E0-$E8
@gl:    lda     glyphs,x
        sta     CHR2 + $E0 * 8,x
        dex
        bpl     @gl
        ldx     #0              ; lettres du scroller (codes $40-$7F)
@sg:    lda     scr_glyphs,x
        sta     CHR2 + $40 * 8,x
        lda     scr_glyphs + 256,x
        sta     CHR2 + $40 * 8 + 256,x
        inx
        bne     @sg
        ldx     #0              ; logo : formes des 10 lettres (codes $80-$A7)
@lg:    lda     logo_glyphs,x
        sta     CHR2 + $80 * 8,x
        inx
        bne     @lg
        ldx     #LOGO_LEN - 256 - 1
@lg2:   lda     logo_glyphs + 256,x
        sta     CHR2 + $80 * 8 + 256,x
        dex
        bpl     @lg2
        ldx     #0
@sc:    lda     $0400,x
        sta     SCR2,x
        lda     $0500,x
        sta     SCR2 + $100,x
        lda     $0600,x
        sta     SCR2 + $200,x
        lda     $0700,x
        sta     SCR2 + $300,x
        inx
        bne     @sc
        ldx     #159            ; lignes 0 à 3 vidées, puis le logo
        lda     #32
@cl:    sta     SCR2,x
        dex
        cpx     #$FF
        bne     @cl
        ldx     #21
@lr:    lda     logo_row0,x
        sta     SCR2 + LOGO_ROW * 40 + LOGO_COL,x
        lda     logo_row1,x
        sta     SCR2 + (LOGO_ROW + 1) * 40 + LOGO_COL,x
        dex
        bpl     @lr
        lda     $DD00
        and     #$FC            ; banque 3
        sta     $DD00
        lda     #$DE            ; écran $F400, caractères $F800
        sta     $D018
        lda     _vis_on         ; vu-mètres : dégradé arc-en-ciel (mémoire couleur)
        beq     @nov
        ldx     #31
@vc:    lda     vucolors,x
        sta     $D800 + 14 * 40 + 3,x
        sta     $D800 + 15 * 40 + 3,x
        sta     $D800 + 16 * 40 + 3,x
        dex
        bpl     @vc
@nov:   rts

; ---------------------------------------------------------------- lecture

_play_run:
        sei
        cld
        ldx     #2
@sv:    lda     $00,x
        sta     zpsave,x
        inx
        bne     @sv

        lda     #$36
        sta     $01
        jsr     silence
        lda     #$7F            ; plus aucune source d'interruption (CIA 1, CIA 2, VIC) : un
        sta     $DC0D           ; morceau qui fait CLI dans son init ne doit pas déclencher
        sta     $DD0D           ; d'IRQ pendant que la ROM du KERNAL est coupée
        lda     $DC0D
        lda     $DD0D
        lda     #0
        sta     $D01A
        lda     #$FF
        sta     $D019

        lda     #<ramirq        ; vecteurs IRQ/NMI/BRK lus en RAM quand la ROM est coupée
        sta     $FFFE
        sta     $FFFA
        lda     #>ramirq
        sta     $FFFF
        sta     $FFFB

        lda     _init_addr
        sta     @ji + 1
        sta     @ji2 + 1
        lda     _init_addr + 1
        sta     @ji + 2
        sta     @ji2 + 2
        lda     _play_addr
        sta     pj + 1
        sta     pj2 + 1
        lda     _play_addr + 1
        sta     pj + 2
        sta     pj2 + 2

        lda     #0              ; remise à zéro des effets
        ldx     #2
@zv:    sta     prevg,x
        sta     state,x
        sta     level,x
        sta     vh,x
        dex
        bpl     @zv

        lda     _vis_on
        beq     @idirect
        lda     #$34            ; E/S en RAM : on capte les écritures vers le SID
        sta     $01
        ldx     #24
        lda     #0
@zr:    sta     $D400,x
        dex
        bpl     @zr
        lda     _song_nr
        sec
        sbc     #1
@ji:    jsr     $0000           ; init (adresse modifiée ci-dessus), A = sous-morceau - 1
        cld
        jsr     sync_sid
        jmp     @idone
@idirect:
        lda     _song_nr
        sec
        sbc     #1
@ji2:   jsr     $0000
        cld
@idone:
        lda     #0
        sta     frames
        sta     frames + 1
        sta     result
        sta     seen
        sta     digits
        sta     digits + 1
        sta     digits + 2
        sta     digits + 3
        lda     _fps
        sta     next
        lda     #0
        sta     next + 1

        jsr     vis_start
        lda     #0
        sta     $D020           ; bordure et fond noirs
        sta     $D021
        lda     $D011
        and     #$7F
        sta     $D011
        sta     stage           ; (A = 0) première interruption : avant le scroller
        lda     #7
        sta     xs
        lda     #<scrtext
        sta     tpos
        lda     #>scrtext
        sta     tpos + 1
        ldx     #0              ; ligne du scroller déjà remplie de texte
@pf:    jsr     next_char
        sta     sbuf,x
        sta     SCRL,x
        lda     nbot
        sta     sbufb,x
        sta     SCRL + 40,x
        inx
        cpx     #40
        bne     @pf
        lda     #LINE_A
        sta     $D012
        lda     #$01
        sta     $D01A
        lda     #$FF
        sta     $D019
        lda     #<irq
        sta     $0314
        lda     #>irq
        sta     $0315
        cli

; attendre le relâchement des touches (celle qui a lancé le morceau précédent)
@rel:   jsr     keys
        bne     @rel

@wait:  jsr     keys
        bne     @key
        lda     frames + 1      ; une seconde de plus ?
        cmp     next + 1
        bcc     @notick
        bne     @dotick
        lda     frames
        cmp     next
        bcc     @notick
@dotick:
        jsr     tick
@notick:
        lda     frames          ; une image de plus : logo et effets
        cmp     seen
        beq     @novis
        sta     seen
        jsr     logocolor
        jsr     scroll_step
        lda     _vis_on
        beq     @novis
        jsr     model
        jsr     render
@novis:
        lda     frames + 1      ; durée atteinte ?
        cmp     _frames_max + 1
        bcc     @wait
        bne     @fin
        lda     frames
        cmp     _frames_max
        bcc     @wait
@fin:   lda     #0
@key:   sta     result

        sei
        lda     #0
        sta     $D01A
        lda     #$FF
        sta     $D019
        lda     #$31
        sta     $0314
        lda     #$EA
        sta     $0315
        lda     #$81
        sta     $DC0D
        lda     $DC0D
        lda     #$FF
        sta     $DC00
        lda     #$36
        sta     $01
        lda     #$C8            ; décalage fin à 0
        sta     $D016
        lda     $DD00
        ora     #$03            ; banque 0
        sta     $DD00
        lda     #$15
        sta     $D018
        jsr     silence
        ldx     #2
@rs:    lda     zpsave,x
        sta     $00,x
        inx
        bne     @rs
        cld
        ldx     #0
        lda     result
        cli
        rts

; IRQ/NMI survenant alors que la ROM est coupée ($01 = $34) : on coupe les sources et on repart.
ramirq:
        pha
        lda     $01
        pha
        lda     #$36
        sta     $01
        lda     #0
        sta     $D01A
        lda     #$FF
        sta     $D019
        lda     #$7F
        sta     $DC0D
        sta     $DD0D
        lda     $DC0D
        lda     $DD0D
        pla
        sta     $01
        pla
        rti

; Chaîne de 3 interruptions raster par image : (0) juste avant la ligne du scroller, on décale
; l'affichage ; (1) à sa dernière ligne, on remet 0 ; (2) en bas d'écran, on appelle le morceau.
; Les écritures dans $D016 doivent tomber dans la bordure (après la fin de la ligne visible),
; d'où les NOP : sinon la ligne en cours est décalée en son milieu.
irq:
        ldx     stage
        beq     irq_a
        dex
        beq     irq_b
        jmp     irq_tune

irq_a:  lda     xs
        ora     #$C8
        nop
        nop
        nop
        sta     $D016
        lda     #1
        sta     stage
        lda     #LINE_B
        bne     irq_next

irq_b:  lda     #$C8
        nop
        nop
        nop
        sta     $D016
        lda     #2
        sta     stage
        lda     #RASTER
irq_next:
        sta     $D012
        lda     #$FF
        sta     $D019
        jmp     $EA81

irq_tune:
        lda     #0
        sta     stage
        lda     #LINE_A
        sta     $D012
        lda     #$FF
        sta     $D019
        lda     _vis_on
        beq     irq_direct
        lda     #$34            ; E/S en RAM pendant le morceau
        sta     $01
pj:     jsr     $0000           ; play (adresse modifiée plus haut)
        jsr     sync_sid        ; copie vers "shadow" et le vrai SID, E/S de nouveau en place
        jmp     irq_count
irq_direct:
pj2:    jsr     $0000
irq_count: inc   frames
        bne     irq_out
        inc     frames + 1
irq_out: jmp    $EA81
