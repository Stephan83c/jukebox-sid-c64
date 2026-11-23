// Client SIDBox2 v2.0 : écrans, cycle réseau (RANDOM3), recherche, touches. Portage de main.c/console.c de la v1.9
// (mêmes textes, couleurs et positions), protocole et contrôles de SPEC-v2.md §6.1, délais §7.7, garde-fou §7.8.
// Exécuté en HISTART..$BFFF avec $01 = $36 (ROM BASIC coupée, KERNAL présent) ; jamais pendant un appel du morceau.

        .const MAX_SECS = 1000
        .const LF = 10
        .const BLACK = 0
        .const WHITE = 1
        .const YELLOW = 7
        .const LIGHTRED = 10
        .const GRAY2 = 12
        .const LIGHTGREEN = 13
        .const LIGHTBLUE = 14
        .const CSCR = $0400

// ---------------------------------------------------------------- console (console.c)

// A = caractère ASCII : écrit en (cx, cy), couleur col, puis avance. Garde X et Y.
cputc: {
        sty     ysave
        cmp     #96
        bcc     l_a
        cmp     #128
        bcs     l_a
        sbc     #31             // (C = 0 ici) minuscules -> majuscules
l_a:    and     #$3F
        pha
        ldy     cy
        lda     rowlo,y
        clc
        adc     cx
        sta     p3
        lda     rowhi,y
        adc     #0
        sta     p3 + 1
        pla
        ldy     #0
        sta     (p3),y
        lda     p3 + 1
        clc
        adc     #>($D800 - CSCR)
        sta     p3 + 1
        lda     col
        sta     (p3),y
        inc     cx
        lda     cx
        cmp     #40
        bcc     l_x
        lda     #0
        sta     cx
        lda     cy
        cmp     #24
        bcs     l_x
        inc     cy
l_x:    ldy     ysave
        rts
}

// Texte qui suit le JSR (ASCII, fini par 0) ; reprend après le 0.
say: {
        pla
        sta     sp_
        pla
        sta     sp_ + 1
l:      inc     sp_
        bne     l_r
        inc     sp_ + 1
l_r:    ldy     #0
        lda     (sp_),y
        beq     l_e
        jsr     cputc
        jmp     l
l_e:    lda     sp_ + 1
        pha
        lda     sp_
        pha
        rts
}

// Texte reçu (p0, au plus X caractères) : minuscules -> majuscules, hors ASCII 32-95 -> « ? » (montrer de la v1.9)
show: {
        ldy     #0
l:      cpx     #0
        beq     l_e
        lda     (p0),y
        beq     l_e
        cmp     #97
        bcc     l_u
        cmp     #123
        bcs     l_u
        sec
        sbc     #32
l_u:    cmp     #32
        bcc     l_q
        cmp     #96
        bcc     l_p
l_q:    lda     #'?'
l_p:    jsr     cputc
        iny
        dex
        jmp     l
l_e:    rts
}

// Efface la ligne Y et place le curseur à son début
clrrow: {
        sty     cy
        lda     #0
        sta     cx
        lda     rowlo,y
        sta     p3
        lda     rowhi,y
        sta     p3 + 1
        lda     #32
        ldy     #39
l:      sta     (p3),y
        dey
        bpl     l
        rts
}

// message(row, couleur, texte) : ligne effacée puis texte à gauche
        .macro message(row, color, text) {
        ldy     #row
        jsr     clrrow
        lda     #color
        sta     col
        jsr     say
        .encoding "ascii"
        .text   text
        .byte   0
        }
// texte à (x, y) en couleur
        .macro at(x, y, color, text) {
        lda     #x
        sta     cx
        lda     #y
        sta     cy
        lda     #color
        sta     col
        jsr     say
        .encoding "ascii"
        .text   text
        .byte   0
        }
        .macro setcol(c) {
        lda     #c
        sta     col
        }
        .macro txt(t) {
        jsr     say
        .encoding "ascii"
        .text   t
        .byte   0
        }

clrscr: {
        ldx     #0
        lda     #32
l:      sta     CSCR,x
        sta     CSCR + $100,x
        sta     CSCR + $200,x
        sta     CSCR + $2E8,x
        inx
        bne     l
        stx     cx
        stx     cy
        rts
}

// deux chiffres de A (0-99)
deux: {
        ldx     #'0'
l:      cmp     #10
        bcc     l_e
        sbc     #10
        inx
        bne     l
l_e:    pha
        txa
        jsr     cputc
        pla
        ora     #'0'
        jmp     cputc
}

// ---------------------------------------------------------------- écrans (main.c)

ecran: {
        lda     #$15            // jeu majuscules/graphiques
        sta     $D018
        lda     #$80            // le KERNAL ne bascule plus avec C= + MAJ
        sta     $0291
        jsr     clrscr
        lda     #BLACK
        sta     $D020
        sta     $D021
        :at(0, 0, WHITE, "SID JUKEBOX V" + VERSION)
        :at(0, 1, LIGHTBLUE, "SERVER ")
        :setcol(LIGHTBLUE)
        lda     #<host
        sta     p0
        lda     #>host
        sta     p0 + 1
        ldx     #32
        jmp     show
}

// Ligne des touches, centrée (37 colonnes) ; LOOP et VIS en vert quand ils sont actifs.
options: {
        :at(1, 24, WHITE, "SPC")
        :setcol(GRAY2)
        :txt("=NEXT ")
        :setcol(WHITE)
        :txt("S")
        :setcol(GRAY2)
        :txt("=SEARCH ")
        :setcol(WHITE)
        :txt("L")
        ldx     #GRAY2
        lda     boucle
        beq     l_1
        ldx     #LIGHTGREEN
l_1:    stx     col
        :txt("=LOOP ")
        :setcol(WHITE)
        :txt("V")
        ldx     #GRAY2
        lda     vis_on
        beq     l_2
        ldx     #LIGHTGREEN
l_2:    stx     col
        :txt("=VIS ")
        :setcol(WHITE)
        :txt("Q")
        :setcol(GRAY2)
        :txt("=QUIT")
        rts
}

// Zone d'effets : lignes 13 à 20 effacées ; avec V, couleurs des 3 barres (lignes 14 à 16) vert / jaune / rouge.
zone_effets: {
        ldx     #0
        lda     #32
l:      sta     CSCR + 13 * 40,x
        sta     CSCR + 13 * 40 + 160,x
        inx
        cpx     #160
        bne     l
        lda     vis_on
        beq     l_e
        ldx     #39
l_c:    lda     #LIGHTGREEN
        cpx     #22
        bcc     l_s
        lda     #YELLOW
        cpx     #32
        bcc     l_s
        lda     #LIGHTRED
l_s:    sta     $D800 + 14 * 40,x
        sta     $D800 + 15 * 40,x
        sta     $D800 + 16 * 40,x
        dex
        bpl     l_c
l_e:    rts
}

// ---------------------------------------------------------------- analyse de l'en-tête OK3 (§6.1)

// champ suivant : q = début, le '|' qui le termine devient 0, p1 avance après lui
field: {
        lda     p1
        sta     q
        lda     p1 + 1
        sta     q + 1
        ldy     #0
l:      lda     (p1),y
        beq     l_e
        cmp     #'|'
        beq     l_b
        inc     p1
        bne     l
        inc     p1 + 1
        bne     l
l_b:    lda     #0
        sta     (p1),y
        inc     p1
        bne     l_e
        inc     p1 + 1
l_e:    rts
}

// champ numérique décimal -> num. Appelé seulement par analyser (getnum) : si le champ est illisible (vide, autre
// chose que des chiffres, > 65535), abandonne l'en-tête (retour dépilé, analyser rend C = 0).
number: {
        jsr     field
        lda     #0
        sta     num
        sta     num + 1
        ldy     #0
        lda     (q),y
        beq     l_bad
l:      lda     (q),y
        beq     l_ok
        sec
        sbc     #'0'
        cmp     #10
        bcs     l_bad
        pha
        lda     num             // num = num * 10 + chiffre
        ldx     num + 1
        asl     num
        rol     num + 1
        bcs     l_ovf
        asl     num
        rol     num + 1
        bcs     l_ovf
        clc
        adc     num
        sta     num
        txa
        adc     num + 1
        sta     num + 1
        bcs     l_ovf
        asl     num
        rol     num + 1
        bcs     l_ovf
        pla
        clc
        adc     num
        sta     num
        bcc     l_n
        inc     num + 1
        beq     l_bad
l_n:    iny
        bne     l
l_ovf:  pla
l_bad:  pla
        pla
        jmp     analyser.bad
l_ok:   rts
}

        .macro getnum(v) {
        jsr     number          // ne revient pas si le champ est illisible (en-tête refusé)
        lda     num
        sta     v
        lda     num + 1
        sta     v + 1
        }
        .macro getstr(v) {
        jsr     field
        lda     q
        sta     v
        lda     q + 1
        sta     v + 1
        }
// C = 1 si a <= b (2 octets chacun) : calcule b - a
        .macro le16(a, b) {
        lda     b
        cmp     a
        lda     b + 1
        sbc     a + 1
        }

// OK3|id|taille|secondes|images/s|sous-morceau|chargement|init|play|relais|taille_relais|complet|titre|auteur|année|scroller
// C = 1 si l'en-tête est accepté (sinon on passe au suivant, socket vivant).
// en-tête refusé (sortie commune d'analyser, placée devant pour des branchements courts)
abad:   clc
        rts
analyser: {
        lda     hdr
        cmp     #'O'
        bne     abad
        lda     hdr + 1
        cmp     #'K'
        bne     abad
        lda     hdr + 2
        cmp     #'3'
        bne     abad
        lda     hdr + 3
        cmp     #'|'
        bne     abad
        lda     #<(hdr + 4)
        sta     p1
        lda     #>(hdr + 4)
        sta     p1 + 1
        :getnum(t_id)
        :getnum(t_size)
        :getnum(t_secs)
        :getnum(t_fps)
        :getnum(t_song)
        :getnum(t_load)
        :getnum(t_init)
        :getnum(t_play)
        :getnum(t_rz)
        :getnum(t_rlen)
        :getnum(t_complet)
        :getstr(t_title)
        :getstr(t_author)
        :getstr(t_released)
        :getstr(t_scroll)
        // ne jamais écrire hors de la zone libre
        lda     t_size
        ora     t_size + 1
        beq     bad2
        lda     t_song + 1
        bne     bad2
        lda     t_song
        beq     bad2
        lda     t_complet + 1
        bne     bad2
        lda     t_complet
        cmp     #2
        bcs     bad2
        lda     t_load + 1
        cmp     #>MEM_BAS
        bcc     bad2
        // t_end = t_load + t_size - 1 <= HIMEM
        clc
        lda     t_load
        adc     t_size
        sta     t_end
        lda     t_load + 1
        adc     t_size + 1
        sta     t_end + 1
        bcs     bad2
        lda     t_end
        bne     l_d1
        dec     t_end + 1
l_d1:   dec     t_end
        :le16(t_end, k_himem)
        bcc     bad2
        // bloc de relais
        lda     t_rlen
        ora     t_rlen + 1
        bne     l_rel
        sta     t_complet               // pas de relais : complet = 0, adresse 0
        sta     t_rz
        sta     t_rz + 1
        sec
        rts
bad2:   clc
        rts
l_rel:  :le16(t_rlen, k_relaymax)
        bcc     bad2
        lda     t_rz + 1
        cmp     #>MEM_BAS
        bcc     bad2
        clc                             // r_end = t_rz + t_rlen - 1 <= HIMEM
        lda     t_rz
        adc     t_rlen
        sta     r_end
        lda     t_rz + 1
        adc     t_rlen + 1
        sta     r_end + 1
        bcs     bad2
        lda     r_end
        bne     l_d2
        dec     r_end + 1
l_d2:   dec     r_end
        :le16(r_end, k_himem)
        bcc     bad2
        // pas de chevauchement : r_end < t_load ou t_rz > t_end
        :le16(t_load, r_end)       // t_load > r_end : bloc avant le morceau
        bcc     l_ok
        :le16(t_rz, t_end)        // t_rz <= t_end : chevauchement
        bcs     bad2
l_ok:   sec
        rts
bad:    clc
        rts
}

k_himem:    .word HIMEM
k_relaymax: .word RELAY_MAX

// Texte du scroller (dans l'en-tête) converti SUR PLACE en indices de glyphes (make_scroll.py) : A-Z = 1-26,
// * . , ! ? - = 27-32, / ' : = 33-35, 0-9 = 36-45, le reste = espace (0) ; $FF à la fin. Vide : texte intégré.
charger_scroll: {
        lda     #0
        sta     _scr_ok
        lda     t_scroll
        sta     p0
        lda     t_scroll + 1
        sta     p0 + 1
        ldy     #0
        lda     (p0),y
        beq     l_x
l:      lda     (p0),y
        beq     l_end
        cmp     #97
        bcc     l_u
        cmp     #123
        bcs     l_u
        sbc     #31             // (C = 1) -32
l_u:    cmp     #65
        bcc     l_s
        cmp     #91
        bcs     l_s
        sbc     #63             // (C = 1) A = 1
        bne     l_st
l_s:    ldx     #8
l_t:    cmp     sym_c,x
        beq     l_f
        dex
        bpl     l_t
        cmp     #48
        bcc     l_z
        cmp     #58
        bcs     l_z
        sbc     #11             // (C = 1) 0 = 36
        bne     l_st
l_f:    txa
        clc
        adc     #27
        bne     l_st
l_z:    lda     #0
l_st:   sta     (p0),y
        iny
        bne     l
l_end:  lda     #$FF
        sta     (p0),y
        lda     p0
        sta     _scr_ptr
        lda     p0 + 1
        sta     _scr_ptr + 1
        lda     #1
        sta     _scr_ok
l_x:    rts
}
sym_c:  .byte '*', '.', ',', '!', '?', '-', '/', $27, ':'

// ---------------------------------------------------------------- réception (recuperer de la v1.9, RANDOM3)

// Demande un morceau, le copie à son adresse et le bloc de relais à la sienne. C = 1 si tout est reçu.
recuperer: {
        lda     #0
        sta     aucun
        sta     occupe
        sta     vieux
        sta     mort
        sta     ok
        lda     #$81            // interruption du CIA 1 (clavier du KERNAL pour la recherche)
        sta     $DC0D
        cli
        jsr     net_open
        bcs     l_open
        clc
        rts
l_open: sta     sock
        lda     rejouer         // rejouer (L, V) : « GET3 <id> » redonne une copie intacte du morceau (un morceau
        beq     l_rnd           // modifie souvent ses propres données en jouant : rejoué depuis la mémoire, il sonne autrement)
        jsr     dec_id
        ldx     #0
l_g1:   lda     cmdg,x
        sta     WDATA,x
        inx
        cpx     #5
        bne     l_g1
        ldy     #0
l_g2:   lda     numbuf,y
        beq     l_lf
        sta     WDATA,x
        inx
        iny
        bne     l_g2
l_rnd:  ldx     #0              // « RANDOM3 <limite> [motif] » + LF, construit dans WDATA
l_c1:   lda     cmd3,x
        sta     WDATA,x
        inx
        cpx     #cmd3_end - cmd3
        bne     l_c1
        ldy     #0
        lda     nfiltre
        beq     l_lf
        lda     #' '
        sta     WDATA,x
        inx
l_c2:   lda     filtre,y
        sta     WDATA,x
        inx
        iny
        cpy     nfiltre
        bne     l_c2
l_lf:   lda     #LF
        sta     WDATA,x
        inx
        lda     sock
        jsr     net_write
        bcs     l_sent
        lda     uci_bloquee
        beq     !+
        jmp     l_dead
!:
        jmp     l_quit
l_sent: lda     #<hdr
        sta     hp
        lda     #>hdr
        sta     hp + 1
        lda     #0
        sta     entete
        lda     #<(10 * T_SEC)  // première ligne : 10 s
        sta     rlim
        lda     #>(10 * T_SEC)
        sta     rlim + 1
        :tstart(tr)
l_read: lda     sock
        jsr     net_read
        bcc     !+
        jmp     l_dead          // socket libéré par l'Ultimate : ne plus y toucher
!:
        sta     n
        bne     l_got
        :toverv(tr, rlim)
        bcc     l_read
        jmp     l_quit          // serveur muet
l_got:  :tstart(tr)
        lda     #<(5 * T_SEC)   // ensuite : 5 s sans octet
        sta     rlim
        lda     #>(5 * T_SEC)
        sta     rlim + 1
        ldx     #0
l_byte: lda     RDATA,x
        ldy     entete
        bne     l_data
        cmp     #LF
        beq     l_eol
        ldy     hp + 1          // en-tête : 299 caractères au plus (le reste est perdu)
        cpy     #>(hdr + 299)
        bne     l_h
        ldy     hp
        cpy     #<(hdr + 299)
        bne     !+
        jmp     l_next
!:
l_h:    ldy     #0
        sta     (hp),y
        inc     hp
        beq     !+
        jmp     l_next
!:
        inc     hp + 1
        jmp     l_next
l_eol:  ldy     #0
        tya
        sta     (hp),y
        stx     xs_
        lda     hdr
        cmp     #'E'
        bne     l_an
        lda     hdr + 4         // ERR|aucun morceau, ERR|trop de requetes, ERR|commande inconnue/indisponible
        cmp     #'a'
        bne     l_e1
        inc     aucun
l_e1:   cmp     #'t'
        bne     l_e2
        inc     occupe
l_e2:   cmp     #'c'
        bne     l_an
        inc     vieux
l_an:   jsr     analyser
        bcc     l_quit          // réponse refusée, socket vivant
        ldx     xs_
        inc     entete
        lda     t_load          // phase 1 : le morceau
        sta     dst
        lda     t_load + 1
        sta     dst + 1
        lda     t_size
        sta     rem
        lda     t_size + 1
        sta     rem + 1
        jmp     l_next
l_data: ldy     #0
        sta     (dst),y
        inc     dst
        bne     l_d1
        inc     dst + 1
l_d1:   lda     rem
        bne     l_d2
        dec     rem + 1
l_d2:   dec     rem
        lda     rem
        ora     rem + 1
        bne     l_next
        lda     entete          // phase terminée
        cmp     #2
        beq     l_done
        lda     t_rlen
        ora     t_rlen + 1
        beq     l_done
        inc     entete          // phase 2 : le bloc de relais
        lda     t_rz
        sta     dst
        lda     t_rz + 1
        sta     dst + 1
        lda     t_rlen
        sta     rem
        lda     t_rlen + 1
        sta     rem + 1
l_next: inx
        cpx     n
        beq     !+
        jmp     l_byte
!:
        jmp     l_read
l_done: inc     ok
l_quit: ldx     #0              // QUIT puis fermeture (jamais sur un socket mort)
l_q:    lda     quit,x
        sta     WDATA,x
        inx
        cpx     #5
        bne     l_q
        lda     sock
        jsr     net_write
        lda     uci_bloquee
        bne     l_dead
        lda     sock
        jsr     net_close
l_dead: lda     ok
        cmp     #1
        rts
}
cmdg:   .encoding "ascii"
        .text   "GET3 "
cmd3:
        .text   "RANDOM3 " + LIMITE
cmd3_end:
quit:   .text   "QUIT"
        .byte   LF

// ---------------------------------------------------------------- recherche (saisir de la v1.9)

saisir: {
        ldx     #0              // attendre le relâchement réel de S (matrice : colonne 1, ligne 5), 50 lectures stables
l_r:    sei
        lda     #$FD
        sta     $DC00
        lda     $DC01
        ldy     #$FF
        sty     $DC00
        cli
        and     #$20
        beq     l_r0
        inx
        cpx     #50
        bne     l_r
        beq     l_go
l_r0:   ldx     #0
        beq     l_r
l_go:   lda     #0
        sta     $C6             // tampon clavier vidé
        sta     nbuf
        jsr     zone_effets_clear
        :at(0, 14, LIGHTBLUE, "SEARCH ARTIST OR TITLE:")
        :at(0, 15, WHITE, "> ")
l_k:    jsr     $FFE4           // GETIN
        beq     l_k
        cmp     #13
        beq     l_ret
        cmp     #3
        beq     l_x
        cmp     #20
        bne     l_ch
        ldx     nbuf
        beq     l_k
        dec     nbuf
        dex
        txa
        clc
        adc     #2
        sta     cx
        lda     #' '
        jsr     cputc
        dec     cx
        jmp     l_k
l_ch:   cmp     #32
        bcc     l_k
        cmp     #91
        bcs     l_k
        ldx     nbuf
        cpx     #30
        bcs     l_k
        sta     SBUF,x
        inc     nbuf
        jsr     cputc
        jmp     l_k
l_ret:  ldx     #0
l_cp:   cpx     nbuf
        beq     l_cpe
        lda     SBUF,x
        sta     filtre,x
        inx
        bne     l_cp
l_cpe:  lda     #0
        sta     filtre,x
        stx     nfiltre
l_x:    rts
}

zone_effets_clear: {
        lda     vis_on
        pha
        lda     #0
        sta     vis_on
        jsr     zone_effets
        pla
        sta     vis_on
        rts
}

// ---------------------------------------------------------------- cycle principal (jukebox de la v1.9)

client_start:
        ldx     #$FF
        txs
        lda     #1
        sta     vis_on
        jsr     clock_init
        jsr     ecran
        jsr     uci_present
        bcs     l_loop
        :message(4, WHITE, "ENABLE COMMAND INTERFACE")
l_hang: jmp     l_hang

l_loop: :message(3, WHITE, "CONNECTING...")
        jsr     recuperer
        bcc     !+
        jmp     l_have
!:
        lda     rejouer         // GET3 refusé : on repart sur un tirage normal
        beq     l_nr
        lda     #0
        sta     rejouer
        sta     aucun
l_nr:   lda     aucun
        beq     l_fail
        :message(3, LIGHTRED, "NO MATCH: ")
        lda     #<filtre
        sta     p0
        lda     #>filtre
        sta     p0 + 1
        ldx     nfiltre
        jsr     show
        :message(4, GRAY2, "PLAYING ANY TUNE INSTEAD")
        lda     #0
        sta     nfiltre
        lda     #1
        sta     perdu
        lda     #4 * T_SEC
        jsr     wait
        jmp     l_loop
l_fail: lda     uci_bloquee
        beq     l_f1
        :message(3, LIGHTRED, "ULTIMATE LOCKED: POWER CYCLE IT")
l_lock: jmp     l_lock
l_f1:   lda     occupe
        beq     l_f2
        :message(3, YELLOW, "SERVER BUSY, WAIT...")
        jmp     l_f4
l_f2:   lda     vieux
        beq     l_f3
        :message(3, LIGHTRED, "SERVER WITHOUT V2.0, RETRYING...")
        jmp     l_f4
l_f3:   :message(3, LIGHTRED, "FAILED, RETRYING...")
l_f4:   lda     #3 * T_SEC
        jsr     wait
        jmp     l_loop

l_have: jsr     ecran
        :at(0, 5, LIGHTBLUE, "TITLE: ")
        :setcol(YELLOW)
        lda     t_title
        ldx     t_title + 1
        ldy     #33
        jsr     showp
        :at(0, 6, LIGHTBLUE, "ARTIST: ")
        :setcol(WHITE)
        lda     t_author
        ldx     t_author + 1
        ldy     #32
        jsr     showp
        :at(0, 7, LIGHTBLUE, "RELEASED: ")
        :setcol(WHITE)
        lda     t_released
        ldx     t_released + 1
        ldy     #30
        jsr     showp
        // cadence du morceau, durée plafonnée, frames_max = secs * fps (additions)
        ldx     #50
        lda     t_fps + 1
        bne     l_fps
        lda     t_fps
        cmp     #60
        bne     l_fps
        ldx     #60
l_fps:  stx     _fps
        lda     t_secs
        sta     secs
        lda     t_secs + 1
        sta     secs + 1
        :le16(secs, k_maxsecs)
        bcs     l_sok
        lda     #<MAX_SECS
        sta     secs
        lda     #>MAX_SECS
        sta     secs + 1
l_sok:  lda     #0
        sta     _frames_max
        sta     _frames_max + 1
        ldx     _fps
l_fm:   clc
        lda     _frames_max
        adc     secs
        sta     _frames_max
        lda     _frames_max + 1
        adc     secs + 1
        sta     _frames_max + 1
        dex
        bne     l_fm
        :at(0, 10, LIGHTBLUE, "TIME: ")
        :setcol(WHITE)
        :txt("00:00 / ")       // le lecteur met à jour ces 5 chiffres (colonne 6, ligne 10)
        ldx     #0              // minutes = secs / 60 (soustractions)
        lda     secs
        sta     num
        lda     secs + 1
        sta     num + 1
l_mn:   lda     num + 1
        bne     l_m1
        lda     num
        cmp     #60
        bcc     l_m2
l_m1:   sec
        lda     num
        sbc     #60
        sta     num
        bcs     l_m3
        dec     num + 1
l_m3:   inx
        bne     l_mn
l_m2:   txa
        jsr     deux
        lda     #':'
        jsr     cputc
        lda     num
        jsr     deux
        :at(0, 11, LIGHTBLUE, "SEARCH: ")
        :setcol(WHITE)
        lda     nfiltre
        beq     l_all
        lda     #<filtre
        ldx     #>filtre
        ldy     nfiltre
        jsr     showp
        jmp     l_sd
l_all:  :txt("ALL")
        lda     perdu
        beq     l_sd
        :setcol(LIGHTRED)
        :txt(" (NO MATCH)")
        lda     #0
        sta     perdu
l_sd:   jsr     zone_effets
        jsr     options
        // paramètres du lecteur
        lda     t_init
        sta     _init_addr
        lda     t_init + 1
        sta     _init_addr + 1
        lda     t_play
        sta     _play_addr
        lda     t_play + 1
        sta     _play_addr + 1
        lda     t_song
        sta     _song_nr
        lda     t_rz
        sta     _relay
        lda     t_rz + 1
        sta     _relay + 1
        lda     t_complet
        sta     _complet
        lda     vis_on
        sta     _vis_on
        jsr     charger_scroll
        jsr     _play_run
        sta     res
        jsr     clock_init      // le lecteur a arrêté les timers du CIA 2
        lda     res
        cmp     #2
        beq     l_quit
        ldx     #0
        stx     rejouer
        cmp     #0
        bne     l_r1
        lda     boucle          // fin du morceau : on le rejoue si la boucle est active
        sta     rejouer
        jmp     l_loop
l_r1:   cmp     #3
        bne     l_r2
        jsr     saisir
        jmp     l_loop
l_r2:   cmp     #4
        bne     l_r3
        lda     boucle
        eor     #1
        sta     boucle
        inc     rejouer
        jmp     l_loop
l_r3:   cmp     #5
        bne     l_r4
        lda     vis_on          // V ne change pas de morceau
        eor     #1
        sta     vis_on
        inc     rejouer
        jmp     l_loop
l_r4:   cmp     #6
        bne     l_r5
        :message(3, LIGHTRED, "TUNE ")      // garde-fou : morceau abandonné, on le signale et on passe au suivant
        jsr     print_id
        :txt(" STUCK, SKIPPED")
        lda     #3 * T_SEC
        jsr     wait
l_r5:   jmp     l_loop

l_quit: jsr     clrscr
        :at(0, 0, WHITE, "GOODBYE")
        jmp     $FCE2           // reset à froid

k_maxsecs: .word MAX_SECS

// texte A/X (bas/haut), au plus Y caractères
showp: {
        sta     p0
        stx     p0 + 1
        tya
        tax
        jmp     show
}

// id du morceau en décimal (sans zéros en tête), à l'écran
print_id: {
        jsr     dec_id
        lda     #<numbuf
        sta     p0
        lda     #>numbuf
        sta     p0 + 1
        ldx     #5
        jmp     show
}

// id du morceau en décimal (sans zéros en tête) dans numbuf, fini par 0
dec_id: {
        lda     #0
        sta     nb_i
        lda     t_id
        sta     num
        lda     t_id + 1
        sta     num + 1
        ldy     #0              // chiffres du plus fort au plus faible
        sty     ttmp
l_d:    ldx     #0
l_s:    lda     num
        sec
        sbc     pow_lo,y
        pha
        lda     num + 1
        sbc     pow_hi,y
        bcc     l_n
        sta     num + 1
        pla
        sta     num
        inx
        bne     l_s
l_n:    pla
        txa
        bne     l_p
        lda     ttmp
        bne     l_p
        cpy     #4
        bne     l_k
l_p:    inc     ttmp
        txa
        ora     #'0'
        ldx     nb_i
        sta     numbuf,x
        inc     nb_i
l_k:    iny
        cpy     #5
        bne     l_d
        ldx     nb_i
        lda     #0
        sta     numbuf,x
        rts
}
pow_lo: .byte <10000, <1000, <100, <10, <1
pow_hi: .byte >10000, >1000, >100, >10, >1

// adresses des lignes de l'écran
rowlo:  .fill 25, <(CSCR + i * 40)
rowhi:  .fill 25, >(CSCR + i * 40)
client_end:
