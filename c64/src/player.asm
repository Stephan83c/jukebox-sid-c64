// Lecteur de SID v2.0 (SIDBox2, étape 3 de SPEC-v2.md) : contrat SPEC-v2.md §7.
// Repris du portage de la v1.8 (étape 1, identique octet pour octet à play.s) avec les ajouts de la v1.9
// (correction de hauteur PAL/NTSC, norme affichée) et les changements de la v2.0 :
//  - plus de capture ($01 = $34) : le morceau est toujours appelé avec $01 = $36 et écrit au vrai SID ; les vu-mètres et la
//    correction de hauteur lisent la copie du bloc de relais posé par le serveur (§5), recopiée dans "shadow" après chaque appel ;
//  - contrat d'état §7.2 : page zéro, pages 2-3, VIC, CIA, $02A6, pile sauvés avant init et restaurés à la fin ;
//  - entre deux appels du morceau, le lecteur tourne avec $01 = $35 (KERNAL coupé) et son IRQ arrive directement par $FFFE :
//    un morceau qui écrase $0314 ou $028F ne peut plus dérouter le lecteur ; une IRQ survenue PENDANT un appel du morceau
//    (morceau qui fait CLI) est acquittée et ignorée (vecteur $FFFE ou $0314 selon $01) ;
//  - tout le lecteur est en $C000-$CFFF (code exécuté autour des appels du morceau : §7.1, vérifié à l'assemblage).

        .const ZPSAVE     = $D200                  // sauvegarde de la page zéro (RAM sous les E/S, §7.1)
        .const WD_INIT    = 45                     // garde-fou : 45 x 65 536 cycles = 3,0 s (PAL) pour init (sidscan refuse au-delà de 2 s)
        .const WD_PLAY    = 8                      // 0,53 s pour play (environ 25 images)
        .const P23SAVE    = $D800                  // sauvegarde des pages 2 et 3 ($D800-$D9FF, RAM sous les E/S)
        .const TIME_OFS   = 10 * 40 + 6            // position du temps écoulé (ligne 10, colonne 6)
        .const LOGO_ROW   = 0                      // le logo occupe les lignes 0 à 2
        .const LOGO_COL   = 9                      // première colonne du logo (11 lettres x 2 colonnes)
        .const LOGO_LEN   = 480                    // octets de formes du logo
        .const RASTER     = 252                    // ligne raster où le morceau est appelé (bas d'écran)
        .const SCROLL_ROW = 19                     // scroller : lettres de 12 pixels de haut sur les lignes 19 et 20
        .const SCR2       = $F400                  // écran de lecture avec effets (RAM sous le KERNAL, banque VIC 3)
        .const CHR2       = $F800                  // jeu de caractères de lecture
        .const SCRL       = SCR2 + SCROLL_ROW * 40
        .const LINE_A     = 50 + 8 * SCROLL_ROW    // juste avant la ligne : on décale l'affichage
        .const LINE_B     = 58 + 8 * (SCROLL_ROW + 1)   // dernière ligne du scroller : on remet le décalage à 0
        .const SPEED      = 2                      // pixels par image
        .const VERLEN     = VERSION.size() + 1     // « V » puis le numéro

// Une barre fine (2 pixels de haut) : vh[vnum] * 1,25 pixels (0-255 -> 0-318) sur 40 cases de 8 pixels (toute la ligne).
// Caractères $E0-$E8 : trait de 0 à 8 pixels de large (voir "glyphs").
        .macro bar(vnum, addr) {
        ldy     #vnum
        lda     vh,y
        lsr
        lsr
        clc
        adc     vh,y            // longueur = vh * 1,25 (9 bits : retenue + A), 0-318 pixels
        sta     tmp2
        ror
        lsr
        lsr
        sta     tmp             // cases pleines (0-39)
        lda     tmp2
        and     #7
        ora     #$E0
        sta     tmp2            // case partielle
        ldx     #0
c:      cpx     tmp
        bcc     full
        beq     part
        lda     #$E0            // vide
        bne     put
part:   lda     tmp2
        bne     put
full:   lda     #$E8            // trait complet
put:    sta     addr,x
        inx
        cpx     #40
        bne     c
        }

player_start:

// Lit le clavier : A = 0 rien, 1 ESPACE, 2 Q, 3 S, 4 C, 5 V (4 = L, boucle).
keys: {
        lda     #$FF            // v2.0 : directions des ports (un morceau peut les avoir changées)
        sta     $DC02
        lda     #0
        sta     $DC03
        lda     #$7F            // colonne 7 : ESPACE (ligne 4), Q (ligne 6)
        sta     $DC00
        lda     $DC01
        tax
        and     #$10
        beq     l_space
        txa
        and     #$40
        beq     l_q
        lda     #$FD            // colonne 1 : S (ligne 5)
        sta     $DC00
        lda     $DC01
        and     #$20
        beq     l_s
        lda     #$DF            // colonne 5 : L (ligne 2)
        sta     $DC00
        lda     $DC01
        and     #$04
        beq     l_c
        lda     #$F7            // colonne 3 : V (ligne 7)
        sta     $DC00
        lda     $DC01
        and     #$80
        beq     l_v
        lda     #0
        rts
l_space: lda     #1
        rts
l_q:     lda     #2
        rts
l_s:     lda     #3
        rts
l_c:     lda     #4
        rts
l_v:     lda     #5
        rts

// Ajoute une seconde au temps écoulé et le réécrit à l'écran.
        }
tick: {
        clc
        lda     next
        adc     _fps
        sta     next
        bcc     l_a
        inc     next + 1
l_a:     inc     digits + 3
        lda     digits + 3
        cmp     #10
        bcc     l_draw
        lda     #0
        sta     digits + 3
        inc     digits + 2
        lda     digits + 2
        cmp     #6
        bcc     l_draw
        lda     #0
        sta     digits + 2
        inc     digits + 1
        lda     digits + 1
        cmp     #10
        bcc     l_draw
        lda     #0
        sta     digits + 1
        inc     digits
l_draw:  lda     digits
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

        }
silence: {
        ldx     #$18
        lda     #0
l_l:     sta     $D400,x
        dex
        bpl     l_l
        rts

        }
// ---------------------------------------------------------------- effets

// Met à jour l'enveloppe simulée, les vu-mètres et l'analyseur à partir de "shadow"
// (v2.0 : recopie de la copie du bloc de relais, faite après chaque appel de play par after_call).
model: {
        lda     #0
        sta     vi
        sta     vo
l_voice: ldy     vi
        ldx     vo
        lda     shadow + 4,x    // contrôle : bit 0 = gate
        and     #1
        sta     tmp
        cmp     prevg,y
        beq     l_gdone
        sta     prevg,y
        lda     tmp
        beq     l_grel
        lda     #1              // gate monte : attaque
        sta     state,y
        bne     l_gdone
l_grel:  lda     #0              // gate descend : relâchement
        sta     state,y
l_gdone: lda     state,y
        beq     l_release
        cmp     #1
        beq     l_attack
        // --- déclin vers le niveau de maintien
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
        sta     tmp2            // niveau de maintien 0-255
        lda     level,y
        cmp     tmp2
        beq     l_levdone
        bcc     l_setsus         // en dessous du maintien
        lda     shadow + 5,x
        and     #$0F
        tax
        lda     level,y
        sec
        sbc     dstep,x
        bcc     l_setsus
        cmp     tmp2
        bcs     l_store
l_setsus: lda    tmp2
l_store: sta     level,y
        jmp     l_levdone
l_attack:
        lda     shadow + 5,x
        lsr
        lsr
        lsr
        lsr
        tax
        lda     level,y
        clc
        adc     astep,x
        bcc     l_astore
        lda     #255            // sommet atteint : déclin
        sta     level,y
        lda     #2
        sta     state,y
        jmp     l_levdone
l_astore: sta    level,y
        jmp     l_levdone
l_release:
        lda     shadow + 6,x
        and     #$0F
        tax
        lda     level,y
        sec
        sbc     dstep,x
        bcs     l_rstore
        lda     #0
l_rstore: sta    level,y
l_levdone:
        // --- hauteur affichée : niveau / 8, 0 si aucune forme d'onde
        ldx     vo
        lda     shadow + 4,x
        and     #$F0
        bne     l_wave
        lda     #0
        beq     l_hset
l_wave:  lda     level,y         // longueur de barre en pixels (0-255)
l_hset:  sta     vh,y
l_nextv: lda     vo
        clc
        adc     #7
        sta     vo
        inc     vi
        lda     vi
        cmp     #3
        beq     l_mend
        jmp     l_voice
l_mend:  rts


// Colonne suivante du scroller : A = case du haut, nbot = case du bas. Le texte est un flux d'indices
// (0 = espace, n = n-ième lettre, $FF = fin, on recommence) ; la lettre n occupe les codes
// 64 + 2 * (n - 1) (haut) et le suivant (bas), ou 168 + 2 * (n - 33) à partir de la 33e. N'utilise ni X ni Y.
// Début du texte : celui du serveur s'il y en a un, sinon le texte intégré. N'utilise que A.
        }
scr_rewind: {
        lda     _scr_ok
        beq     l_def
        lda     _scr_ptr
        sta     tpos
        lda     _scr_ptr + 1
        sta     tpos + 1
        rts
l_def:   lda     #<scrtext
        sta     tpos
        lda     #>scrtext
        sta     tpos + 1
        rts

        }
next_char: {
        lda     tpos
        sta     l_rd + 1
        lda     tpos + 1
        sta     l_rd + 2
l_rd:    lda.abs     $0000
        cmp     #$FF
        bne     l_ok
        jsr     scr_rewind
        jmp     next_char
l_ok:    inc     tpos
        bne     l_x
        inc     tpos + 1
l_x:     cmp     #0
        bne     l_gl
        lda     #32
        sta     nbot
        rts
l_gl:    cmp     #33
        bcs     l_hi
        asl
        clc
        adc     #62             // lettres 1-32 : codes 64 + 2 * (n - 1)
        jmp     l_st
l_hi:    asl
        clc
        adc     #102            // lettres 33 et suivantes : codes 168 + 2 * (n - 33) ($A8...)
l_st:    sta     nbot
        inc     nbot
        rts

// Une image de scroller : décalage fin ; tous les 8 pixels, le texte glisse d'une colonne.
        }
scroll_step: {
        lda     xs
        sec
        sbc     #SPEED
        bcs     l_store
        clc
        adc     #8
        pha
        ldx     #0
l_sh:    lda     sbuf + 1,x
        sta     sbuf,x
        lda     sbufb + 1,x
        sta     sbufb,x
        inx
        cpx     #39
        bne     l_sh
        jsr     next_char
        sta     sbuf + 39
        lda     nbot
        sta     sbufb + 39
        ldx     #39             // recopie vers l'écran (en écriture seulement : sous la ROM)
l_cp:    lda     sbuf,x
        sta     SCRL,x
        lda     sbufb,x
        sta     SCRL + 40,x
        dex
        bpl     l_cp
        pla
l_store: sta     xs
        // couleurs des deux lignes : arc-en-ciel qui tourne
        lda     frames
        lsr
        sta     tmp
        ldx     #39
l_co:    txa
        clc
        adc     tmp
        and     #7
        tay
        lda     rainbow,y
        sta     $D800 + SCROLL_ROW * 40,x
        sta     $D800 + SCROLL_ROW * 40 + 40,x
        dex
        bpl     l_co
        rts

// Couleurs du logo : un arc-en-ciel qui défile (changement tous les 4 images).
        }
logocolor: {
        lda     frames
        lsr
        lsr
        sta     tmp
        ldx     #0
l_l:     txa
        clc
        adc     tmp
        and     #7
        tay
        lda     rainbow,y
        sta     $D800 + LOGO_ROW * 40 + LOGO_COL,x
        sta     $D800 + (LOGO_ROW + 1) * 40 + LOGO_COL,x
        sta     $D800 + (LOGO_ROW + 2) * 40 + LOGO_COL,x
        inx
        cpx     #22
        bne     l_l
        rts

        }
render: {
        :bar(0, SCR2 + 14 * 40)
        :bar(1, SCR2 + 15 * 40)
        :bar(2, SCR2 + 16 * 40)
        rts

// Passage à l'écran de lecture : jeu de caractères (ROM recopiée + traits), copie de l'écran
// courant, banque VIC 3 ($C000-$FFFF), écran en $F400, caractères en $F800.
        }
vis_start: {
        lda     #$31            // ROM des caractères visible en $D000 (ni BASIC ni KERNAL)
        sta     $01
        ldx     #0
l_cc:    lda     $D000,x
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
        bne     l_cc
        lda     #$35
        sta     $01
        ldx     #71             // 9 traits : codes $E0-$E8
l_gl:    lda     glyphs,x
        sta     CHR2 + $E0 * 8,x
        dex
        bpl     l_gl
        ldx     #0              // lettres du scroller (codes $40-$7F)
l_sg:    lda     scr_glyphs,x
        sta     CHR2 + $40 * 8,x
        lda     scr_glyphs + 256,x
        sta     CHR2 + $40 * 8 + 256,x
        inx
        bne     l_sg
        ldx     #0              // 13 lettres de plus (/ ' : 0-9) : codes $A8-$C1 (208 octets)
l_sh:    lda     scr_glyphs + 512,x
        sta     CHR2 + $A8 * 8,x
        inx
        cpx     #208
        bne     l_sh
        ldx     #0              // logo : formes des 10 lettres (codes $80-$A7 puis $C2-$D5)
l_lg:    lda     logo_glyphs,x
        sta     CHR2 + $80 * 8,x
        inx
        bne     l_lg
        ldx     #63
l_lg2:   lda     logo_glyphs + 256,x
        sta     CHR2 + $80 * 8 + 256,x
        dex
        bpl     l_lg2
        ldx     #0
l_lg3:   lda     logo_glyphs + 320,x
        sta     CHR2 + $C2 * 8,x
        inx
        cpx     #LOGO_LEN - 320
        bne     l_lg3
        ldx     #0
l_sc:    lda     $0400,x
        sta     SCR2,x
        lda     $0500,x
        sta     SCR2 + $100,x
        lda     $0600,x
        sta     SCR2 + $200,x
        lda     $0700,x
        sta     SCR2 + $300,x
        inx
        bne     l_sc
        ldx     #159            // lignes 0 à 3 vidées, puis le logo
        lda     #32
l_cl:    sta     SCR2,x
        dex
        cpx     #$FF
        bne     l_cl
        ldx     #21
l_lr:    lda     logo_row0,x
        sta     SCR2 + LOGO_ROW * 40 + LOGO_COL,x
        lda     logo_row1,x
        sta     SCR2 + (LOGO_ROW + 1) * 40 + LOGO_COL,x
        lda     logo_row2,x
        sta     SCR2 + (LOGO_ROW + 2) * 40 + LOGO_COL,x
        dex
        bpl     l_lr
        ldx     #VERLEN - 1     // version, en haut à droite (gris)
l_ve:    lda     version,x
        sta     SCR2 + 39 - (VERLEN - 1),x
        lda     #$0C
        sta     $D800 + 39 - (VERLEN - 1),x
        dex
        bpl     l_ve
        lda     $DD00
        and     #$FC            // banque 3
        sta     $DD00
        lda     #$DE            // écran $F400, caractères $F800
        sta     $D018
        lda     _vis_on         // vu-mètres : dégradé arc-en-ciel (mémoire couleur)
        beq     l_nov
        ldx     #39
l_vc:    lda     vucolors,x
        sta     $D800 + 14 * 40,x
        sta     $D800 + 15 * 40,x
        sta     $D800 + 16 * 40,x
        dex
        bpl     l_vc
l_nov:  ldy     #0              // après le temps : norme de la machine, puis cadence du morceau (v1.9)
        lda     mfps
        cmp     #60
        bne     l_pl
        ldy     #5
l_pl:   ldx     #0
l_pn:   lda     normes,y
        sta     SCR2 + 10 * 40 + 21,x
        lda     #$0C
        sta     $D800 + 10 * 40 + 21,x
        iny
        inx
        cpx     #5
        bne     l_pn
        ldy     #0
        lda     _fps
        cmp     #60
        bne     l_pt
        ldy     #4
l_pt:   lda     cadences,y
        sta     SCR2 + 10 * 40 + 21,x
        lda     #$0C
        sta     $D800 + 10 * 40 + 21,x
        iny
        inx
        cpx     #9
        bne     l_pt
        rts

// ---------------------------------------------------------------- lecture

        }
// ---------------------------------------------------------------- lecture

// Joue le morceau décrit par _init_addr, _play_addr, _song_nr, _fps, _frames_max, _relay, _complet.
// Rend A = 0 (durée atteinte), 1 ESPACE, 2 Q, 3 S, 4 L, 5 V, 6 morceau abandonné (garde-fou) ; X = 0 ; $01 = $36 ;
// état §7.2 restauré.
_play_run: {
        sei
        cld
        tsx
        stx     spsave
        // --- sauvegardes (§7.2) : page zéro et pages 2-3 dans la RAM sous les E/S
        lda     #$34
        sta     $01
        ldx     #2
l_sz:   lda     $00,x
        sta     ZPSAVE,x
        inx
        bne     l_sz
l_sp:   lda     $0200,x
        sta     P23SAVE,x
        lda     $0300,x
        sta     P23SAVE + $100,x
        inx
        bne     l_sp
        lda     #$35
        sta     $01
        ldx     #VREGS - 1      // registres du VIC
l_sv:   ldy     vregs,x
        lda     $D000,y
        sta     vsave,x
        dex
        bpl     l_sv
        lda     $DD00
        sta     dd00save
        lda     $DD02
        sta     dd02save

        jsr     silence
        lda     #$7F            // plus aucune source d'interruption (CIA 1, CIA 2, VIC)
        sta     $DC0D
        sta     $DD0D
        lda     $DC0D
        lda     $DD0D
        lda     #0
        sta     $D01A
        lda     #$FF
        sta     $D019

        jsr     vectors
        lda     #<nmi           // NMI avec le KERNAL visible : ignorées aussi
        sta     $0318
        lda     #>nmi
        sta     $0319
        lda     #<kirq          // IRQ pendant un appel du morceau avec le KERNAL visible ($01 = $36)
        sta     $0314
        lda     #>kirq
        sta     $0315

        lda     _init_addr
        sta     l_ji + 1
        lda     _init_addr + 1
        sta     l_ji + 2
        lda     _play_addr
        sta     pj + 1
        lda     _play_addr + 1
        sta     pj + 2

        // cadence de la machine, mesurée avant init (§7.6) : en PAL le raster monte jusqu'à la ligne 311, en NTSC 262
        lda     #50
        sta     mfps
l_d1:   lda     $D011
        bpl     l_d1            // attendre la moitié basse de l'image (lignes >= 256)
l_d2:   lda     $D011
        bpl     l_dntsc         // revenu en haut : l'image s'arrêtait avant la ligne 288
        lda     $D012
        cmp     #$20
        bcc     l_d2
        bcs     l_dok           // ligne >= 288 : PAL
l_dntsc: lda    #60
        sta     mfps
l_dok:
        // $02A6 = norme du morceau (1 PAL, 0 NTSC), restauré avec la page 2 (§7.6)
        ldx     #1
        lda     _fps
        cmp     #60
        bne     l_a6
        dex
l_a6:   stx     $02A6

        // copie du bloc de relais : source de "shadow", mise à zéro avant init ; correction de hauteur si complet = 1
        lda     #0
        sta     hasrel
        sta     dofix
        ldx     #24
l_zs:   sta     shadow,x
        dex
        bpl     l_zs
        lda     _relay + 1
        beq     l_norel
        sta     l_zc + 2
        sta     after_call.l_c + 2
        lda     _relay
        sta     l_zc + 1
        sta     after_call.l_c + 1
        lda     #0
        ldx     #31
l_zc:   sta     $FFFF,x
        dex
        bpl     l_zc
        inc     hasrel
        lda     _complet
        beq     l_norel
        lda     _fps
        cmp     mfps
        beq     l_norel
        inc     dofix
l_norel:

        lda     #0              // remise à zéro des effets et du journal
        sta     port_play
        ldx     #2
l_zv:   sta     prevg,x
        sta     state,x
        sta     level,x
        sta     vh,x
        dex
        bpl     l_zv

        // --- init (§7.3), sous garde-fou (§7.8 : 3 s)
        ldy     #WD_INIT
        jsr     wd_arm
        lda     #$36
        sta     $01
        lda     #1
        sta     incall
        lda     _song_nr
        sec
        sbc     #1
l_ji:   jsr     $0000           // init (adresse modifiée ci-dessus), A = sous-morceau - 1
        sei
        ldx     $01
        stx     port_init
        lda     #$35
        sta     $01
        cld
        lda     #0
        sta     incall
        jsr     wd_off
        jsr     after_call

        lda     #0
        sta     frames
        sta     frames + 1
        sta     tframes
        sta     tframes + 1
        sta     acc
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
        jsr     vectors         // le jeu de caractères ($F800-$FFFF) recouvre les vecteurs : les réécrire
        lda     #0
        sta     $D020           // bordure et fond noirs
        sta     $D021
        lda     $D011
        and     #$7F
        sta     $D011
        sta     stage           // (A = 0) première interruption : avant le scroller
        lda     #7
        sta     xs
        jsr     scr_rewind
        ldx     #0              // ligne du scroller déjà remplie de texte
l_pf:   jsr     next_char
        sta     sbuf,x
        sta     SCRL,x
        lda     nbot
        sta     sbufb,x
        sta     SCRL + 40,x
        inx
        cpx     #40
        bne     l_pf
        lda     #LINE_A
        sta     $D012
        lda     #$01
        sta     $D01A
        lda     #$FF
        sta     $D019
        cli

// attendre le relâchement des touches (celle qui a lancé le morceau précédent)
l_rel:  jsr     keys
        bne     l_rel

l_wait: jsr     keys
        bne     l_key
        lda     tframes + 1     // une seconde de plus ?
        cmp     next + 1
        bcc     l_notick
        bne     l_dotick
        lda     tframes
        cmp     next
        bcc     l_notick
l_dotick:
        jsr     tick
l_notick:
        lda     frames          // une image de plus : logo et effets
        cmp     seen
        beq     l_novis
        sta     seen
        jsr     logocolor
        jsr     scroll_step
        lda     _vis_on
        beq     l_novis
        jsr     model
        jsr     render
l_novis:
        lda     tframes + 1     // durée atteinte ?
        cmp     _frames_max + 1
        bcc     l_wait
        bne     l_fin
        lda     tframes
        cmp     _frames_max
        bcc     l_wait
l_fin:  lda     #0
l_key:  sta     result

        // --- fin : restauration de l'état (§7.2)
        sei
        lda     #0
        sta     $D01A
        lda     #$FF
        sta     $D019
        jsr     silence
        lda     #$7F            // CIA 2 : aucune NMI d'un morceau ne survit, timers arrêtés, banque VIC remise
        sta     $DD0D
        lda     $DD0D
        lda     #$08
        sta     $DD0E
        sta     $DD0F
        lda     dd02save
        sta     $DD02
        lda     dd00save
        sta     $DD00
        ldx     #VREGS - 1      // VIC
l_rv:   ldy     vregs,x
        lda     vsave,x
        sta     $D000,y
        dex
        bpl     l_rv
        lda     #$FF
        sta     $D019
        lda     #$34            // page zéro, pages 2-3 ($02A6, $0314, $028F...) : tout en RAM pour les relire
        sta     $01
        ldx     #2
l_rz:   lda     ZPSAVE,x
        sta     $00,x
        inx
        bne     l_rz
l_rp:   lda     P23SAVE,x
        sta     $0200,x
        lda     P23SAVE + $100,x
        sta     $0300,x
        inx
        bne     l_rp
        lda     #$36
        sta     $01
        lda     #$7F            // CIA 1 : valeurs du KERNAL (IOINIT), timer A selon $02A6 restauré
        sta     $DC0D
        lda     #$08
        sta     $DC0F
        ldx     #$25
        ldy     #$40
        lda     $02A6
        bne     l_pal
        ldx     #$95
        ldy     #$42
l_pal:  stx     $DC04
        sty     $DC05
        lda     $DC0E
        and     #$80
        ora     #$11
        sta     $DC0E
        lda     #$FF
        sta     $DC02
        sta     $DC00
        lda     #0
        sta     $DC03
        lda     $DC0D
        lda     #$81
        sta     $DC0D
        ldx     spsave          // pile
        txs
        cld
        ldx     #0
        lda     result
        cli
        rts
        }

// Vecteurs matériels en RAM (lus quand le KERNAL est coupé) : IRQ du lecteur, NMI ignorées (RESTORE compris).
// Les octets $FFFA-$FFFF sont aussi la fin de la forme du caractère $FF de CHR2 (inversé, jamais affiché).
vectors: {
        lda     #<irq
        sta     $FFFE
        lda     #>irq
        sta     $FFFF
        lda     #<nmi
        sta     $FFFA
        lda     #>nmi
        sta     $FFFB
        rts
}

// Après chaque appel du morceau ($01 = $35) : copie du bloc de relais -> "shadow", puis correction de hauteur (§7.6)
// en réécrivant les 6 registres de fréquence (le morceau vient d'y écrire les valeurs non corrigées).
after_call: {
        lda     hasrel
        beq     l_x
        ldx     #24
l_c:    lda     $FFFF,x         // adresse de la copie (modifiée par _play_run)
        sta     shadow,x
        dex
        bpl     l_c
        lda     dofix
        beq     l_x
        jsr     fixpitch
        lda     shadow
        sta     $D400
        lda     shadow + 1
        sta     $D401
        lda     shadow + 7
        sta     $D407
        lda     shadow + 8
        sta     $D408
        lda     shadow + 14
        sta     $D40E
        lda     shadow + 15
        sta     $D40F
l_x:    rts
}

// Hauteur (v1.9) : l'horloge du SID suit la machine (PAL 985 kHz, NTSC 1023 kHz, rapport 1,038).
// On corrige les fréquences des 3 voix dans "shadow" : v - (v + v/4)/32 = x0,961 (morceau PAL sur
// machine NTSC) ou v + (v + v/4)/32 = x1,039 (morceau NTSC sur machine PAL, plafonné à $FFFF).
fixpitch: {
        ldx     #14
l_v:    lda     shadow + 1,x
        lsr
        sta     fp2
        lda     shadow,x
        ror
        lsr     fp2
        ror                     // fp2:A = v / 4
        clc
        adc     shadow,x
        sta     fp1
        lda     fp2
        adc     shadow + 1,x    // retenue = bit 16
        ror
        sta     fp2
        ror     fp1
        ldy     #4
l_s:    lsr     fp2
        ror     fp1
        dey
        bne     l_s             // fp2:fp1 = (v + v/4) / 32
        lda     _fps
        cmp     mfps
        bcs     l_up            // morceau 60 Hz sur machine 50 Hz : plus aigu
        sec
        lda     shadow,x
        sbc     fp1
        sta     shadow,x
        lda     shadow + 1,x
        sbc     fp2
        bcs     l_st            // (toujours)
l_up:   clc
        lda     shadow,x
        adc     fp1
        sta     shadow,x
        lda     shadow + 1,x
        adc     fp2
        bcc     l_st
        lda     #$FF
        sta     shadow,x
l_st:   sta     shadow + 1,x
        txa
        sec
        sbc     #7
        tax
        bpl     l_v
        rts
}

// IRQ survenue pendant un appel du morceau, KERNAL visible (entrée par $FF48 puis $0314, A X Y empilés) : acquittée, ignorée.
kirq: {
        lda     #$FF
        sta     $D019
        lda     $DC0D
        lda     $DD0D
        jmp     $EA81
}

// Garde-fou (§7.8, décision D6) : pendant chaque appel du morceau, le timer B du CIA 2 compte Y débordements du
// timer A (65 536 cycles chacun) puis déclenche une NMI. Si l'appel n'est pas fini, on l'abandonne : pile remise à
// l'entrée de _play_run, état restauré, résultat 6. Désarmé après l'appel : aucune NMI en lecture normale.
wd_arm: {
        lda     #$7F
        sta     $DD0D
        lda     $DD0D
        lda     #$FF
        sta     $DD04
        sta     $DD05
        sty     $DD06
        lda     #0
        sta     $DD07
        lda     #$59            // timer B : démarré, chargé, une seule fois, compte les débordements du timer A
        sta     $DD0F
        lda     #$11            // timer A : démarré, chargé, continu
        sta     $DD0E
        lda     #$82            // NMI au débordement du timer B
        sta     $DD0D
        rts
}
wd_off: {
        lda     #$7F
        sta     $DD0D
        lda     #$08
        sta     $DD0E
        sta     $DD0F
        lda     $DD0D
        rts
}

// NMI (par $FFFA ou $0318) : seule celle du garde-fou pendant un appel compte ; les autres (RESTORE...) sont ignorées.
nmi: {
        pha
        lda     $01
        pha
        lda     #$35
        sta     $01
        lda     $DD0D           // acquitte ; bit 1 = timer B
        and     #$02
        beq     l_out
        lda     incall
        bne     l_abort
l_out:  pla
        sta     $01
        pla
        rti
l_abort:
        jsr     wd_off
        lda     #0
        sta     incall
        cld
        ldx     spsave          // on abandonne tout ce qui est empilé depuis l'entrée de _play_run
        txs
        lda     #6
        jmp     _play_run.l_key
}

// Chaîne de 3 interruptions raster par image : (0) juste avant la ligne du scroller, on décale
// l'affichage ; (1) à sa dernière ligne, on remet 0 ; (2) en bas d'écran, on appelle le morceau.
// Les écritures dans $D016 doivent tomber dans la bordure (après la fin de la ligne visible),
// d'où les NOP : sinon la ligne en cours est décalée en son milieu.
// Entrée directe par $FFFE ($01 = $35 hors des appels du morceau). Pendant un appel (incall), le morceau a fait CLI :
// on acquitte (E/S rendues visibles le temps de l'acquittement) et on repart sans rien faire.
irq: {
        pha
        lda     incall
        bne     l_in
        txa
        pha
        tya
        pha
        ldx     stage
        beq     irq_a
        dex
        beq     irq_b
        jmp     irq_tune
l_in:   lda     $01
        pha
        lda     #$35
        sta     $01
        lda     #$FF
        sta     $D019
        lda     $DC0D
        lda     $DD0D
        pla
        sta     $01
        pla
        rti
        }
irq_a: {  lda     xs
        ora     #$C8
        nop
        nop
        nop
        sta     $D016
        lda     #1
        sta     stage
        lda     #LINE_B
        bne     irq_next

        }
irq_b: {  lda     #$C8
        nop
        nop
        nop
        sta     $D016
        lda     #2
        sta     stage
        lda     #RASTER
        }
irq_next: {
        sta     $D012
        lda     #$FF
        sta     $D019
        }
irq_exit: {
        pla
        tay
        pla
        tax
        pla
        rti
        }

irq_tune: {
        lda     #0
        sta     stage
        lda     #LINE_A
        sta     $D012
        lda     #$FF
        sta     $D019
        inc     frames
        bne     irq_cad
        inc     frames + 1
// Le morceau est appelé à SA cadence (fps), pas à celle de la machine (mfps) : on ajoute fps à
// l'accumulateur à chaque image, et on appelle le morceau chaque fois qu'il atteint mfps
// (PAL/50 sur NTSC : une image sur six sans appel ; NTSC/60 sur PAL : parfois deux appels).
        }
irq_cad: {
        cld
        clc
        lda     acc
        adc     _fps
        sta     acc
        }
irq_again: {
        cld
        lda     acc
        cmp     mfps
        bcc     irq_exit
        sec
        sbc     mfps
        sta     acc
        ldy     #WD_PLAY        // garde-fou (§7.8 : 0,53 s, environ 25 images)
        jsr     wd_arm
        lda     #$36            // appel du morceau (§7.3) : E/S visibles, ROM BASIC coupée, KERNAL présent
        sta     $01
        lda     #1
        sta     incall
        }
pj: {     jsr     $0000           // play (adresse modifiée plus haut)
        sei
        ldx     $01
        cpx     #$36
        beq     l_p
        stx     port_play
l_p:    lda     #$35
        sta     $01
        cld
        lda     #0
        sta     incall
        jsr     wd_off
        jsr     after_call
        inc     tframes
        bne     irq_again
        inc     tframes + 1
        jmp     irq_again
        }

// ---- données
vregs:  .byte $11, $15, $16, $18, $20, $21     // registres du VIC sauvés et restaurés (§7.2)
        .label VREGS = 6
normes: .byte $10, $01, $0C, $20, $20, $0E, $14, $13, $03, $20   // « PAL  », « NTSC » (codes écran, majuscules de la ROM)
cadences: .byte $35, $30, $08, $1A, $36, $30, $08, $1A          // « 50HZ », « 60HZ »
version: .byte 22                      // V (code écran)
        .encoding "screencode_upper"
        .text VERSION
// pas par image (20 ms) : attaque (2 ms .. 8 s) puis déclin/relâchement (6 ms .. 24 s)
astep:  .byte 255, 255, 255, 212, 134, 91, 75, 64, 51, 20, 10, 6, 5, 2, 1, 1
dstep:  .byte 255, 212, 106, 71, 45, 30, 25, 21, 17, 7, 3, 2, 2, 1, 1, 1
// traits de 0 à 8 pixels de large, 2 pixels de haut (lignes 3 et 4 de la case)
glyphs: .byte 0,0,0,$00,$00,0,0,0
        .byte 0,0,0,$80,$80,0,0,0
        .byte 0,0,0,$C0,$C0,0,0,0
        .byte 0,0,0,$E0,$E0,0,0,0
        .byte 0,0,0,$F0,$F0,0,0,0
        .byte 0,0,0,$F8,$F8,0,0,0
        .byte 0,0,0,$FC,$FC,0,0,0
        .byte 0,0,0,$FE,$FE,0,0,0
        .byte 0,0,0,$FF,$FF,0,0,0

// couleurs du logo et du scroller (défilent)
rainbow: .byte 10, 4, 14, 3, 5, 7, 8, 2
// Dégradé arc-en-ciel des vu-mètres, une couleur par case (40 cases), sans noir.
vucolors:
        .byte   4, 4, 4, 4, 4, 6, 6, 6
        .byte   6, 14, 14, 14, 14, 3, 3, 3
        .byte   3, 5, 5, 5, 5, 13, 13, 13
        .byte   13, 7, 7, 7, 7, 8, 8, 8
        .byte   8, 8, 2, 2, 2, 2, 2, 2

// Appel du banc VICE (tools/banc.py), placé ici parce qu'un morceau chargé en $0800 écrase le programme de démo.
bench_wait:
        jmp     bench_wait      // attente pendant que le banc charge le morceau (qui peut recouvrir $0800-...)
bench:  sei
        jsr     _play_run
        sta     bench_ret
        inc     bench_done
        cli
!:      jmp     !-
bench_ret:  .byte 0
bench_done: .byte 0

#import "logo.asm"
#import "scroll.asm"
player_end:

// ---- variables (BSS : pas d'octets dans le fichier, adresses à la suite de l'image)
        .label bss_start = *
