// Ultimate Command Interface ($DF1C-$DF1F), cible réseau : portage de uci.c de la v1.9 (SPEC.md §5.3, SPEC-v2.md §7.7).
// $DF1C contrôle (écriture) / état (lecture) ; $DF1D commande / identification $C9 ; $DF1E réponse ; $DF1F statut texte.
// Chaque attente a une limite, comptée sur l'horloge du CIA 2 (décision D4) et non sur l'IRQ du KERNAL.

        .const UCI_CTRL = $DF1C
        .const UCI_CMD  = $DF1D
        .const UCI_RESP = $DF1E
        .const UCI_STAT = $DF1F
        .const REP_MAX  = 128
        .const STAT_MAX = 16
        .label RDATA = rep + 2          // données lues par net_read
        .label WDATA = cmd + 3          // données à écrire par net_write

// ---------------------------------------------------------------- horloge (D4)
// Timers A et B du CIA 2 enchaînés, en compteur libre : B compte les débordements de A (65 536 cycles, environ 66 ms).
// Fonctionne sans IRQ ni NMI (aucune source activée). À relancer après chaque morceau (le lecteur arrête les timers).
        .const T_SEC = 15                         // unités d'horloge par seconde (66,5 ms en PAL, 64 ms en NTSC)

clock_init: {
        lda     #$7F
        sta     $DD0D
        lda     #$FF
        sta     $DD04
        sta     $DD05
        sta     $DD06
        sta     $DD07
        lda     #$51            // timer B : démarré, chargé, continu, compte les débordements du timer A
        sta     $DD0F
        lda     #$11            // timer A : démarré, chargé, continu
        sta     $DD0E
        lda     $DD0D
        rts
}

// A (bas) / X (haut) = horloge qui monte (complément du timer B, relu tant que l'octet haut change)
clock: {
l:      ldx     $DD07
        lda     $DD06
        cpx     $DD07
        bne     l
        eor     #$FF
        pha
        txa
        eor     #$FF
        tax
        pla
        rts
}

// départ d'une attente : var (2 octets) = horloge
        .macro tstart(v) {
        jsr     clock
        sta     v
        stx     v + 1
        }
// C = 1 si au moins « limit » unités se sont écoulées depuis var (limit constant)
        .macro tover(v, lim) {
        jsr     clock
        sec
        sbc     v
        sta     ttmp
        txa
        sbc     v + 1
        cmp     #>lim
        bne     d
        lda     ttmp
        cmp     #<lim
d:
        }
// idem, limite dans une variable de 2 octets
        .macro toverv(v, lv) {
        jsr     clock
        sec
        sbc     v
        sta     ttmp
        txa
        sbc     v + 1
        cmp     lv + 1
        bne     d
        lda     ttmp
        cmp     lv
d:
        }

// attend A unités d'horloge
wait: {
        sta     wlim
        lda     #0
        sta     wlim + 1
        :tstart(tw)
l:      :toverv(tw, wlim)
        bcc     l
        rts
}

// ---------------------------------------------------------------- Command Interface

// C = 1 si l'interface répond (option « Command Interface » activée)
uci_present: {
        lda     UCI_CMD
        cmp     #$C9
        beq     y
        clc
        rts
y:      sec
        rts
}

// attend que l'Ultimate prenne l'acquittement (bit 1 retombe), 2 s au plus ; C = 0 si bloqué
uci_ack: {
        lda     #$02
        sta     UCI_CTRL
        :tstart(ta)
l:      lda     UCI_CTRL
        and     #$02
        beq     ok
        :tover(ta, 2 * T_SEC)
        bcc     l
        jmp     uci_lock
ok:     sec
        rts
}

// l'Ultimate ne répond plus dans le délai : abandon de la commande, drapeau uci_bloquee
uci_lock: {
        lda     #$04
        sta     UCI_CTRL
        lda     #1
        sta     uci_bloquee
        clc
        rts
}

// Envoie cmd[0..X-1], lit la réponse dans rep (rep_n octets) et le statut dans ustat. Limite de traitement : ulim.
// C = 1 si le statut commence par « 00 ».
uci_exec: {
        stx     un
        lda     #0
        sta     rep_n
        sta     stat_n
        sta     ustat
        :tstart(tu)                     // attendre l'état repos (2 s)
l_idle: lda     UCI_CTRL
        and     #$30
        beq     l_send
        and     #$20
        beq     l_busy
        lda     #$02                    // données d'une commande précédente : acquitter
        sta     UCI_CTRL
l_busy: :tover(tu, 2 * T_SEC)
        bcc     l_idle
        jmp     uci_lock
l_send: ldx     #0
l_wc:   lda     cmd,x
        sta     UCI_CMD
        inx
        cpx     un
        bne     l_wc
        lda     #$01                    // PUSH
        sta     UCI_CTRL
        lda     UCI_CTRL
        and     #$08
        beq     l_go
        lda     #$08                    // erreur : effacer
        sta     UCI_CTRL
        clc
        rts
l_go:   :tstart(tu)
l_wait: lda     UCI_CTRL                // fin du traitement : état 10 ou 11
        sta     us
        and     #$20
        bne     l_data
        :toverv(tu, ulim)
        bcc     l_wait
        jmp     uci_lock
l_data: lda     UCI_CTRL
        bpl     l_stat
        lda     UCI_RESP
        ldx     rep_n
        cpx     #REP_MAX
        bcs     l_data
        sta     rep,x
        inc     rep_n
        jmp     l_data
l_stat: bit     UCI_CTRL
        bvc     l_more
        lda     UCI_STAT
        ldx     stat_n
        cpx     #STAT_MAX
        bcs     l_stat
        sta     ustat,x
        inc     stat_n
        jmp     l_stat
l_more: lda     us
        and     #$30
        cmp     #$30                    // encore des données : acquitter et continuer
        bne     l_end
        jsr     uci_ack
        bcc     l_ko
        :tstart(tu)
        jmp     l_wait
l_end:  ldx     stat_n
        lda     #0
        sta     ustat,x
        jsr     uci_ack
        bcc     l_ko
        lda     ustat
        cmp     #'0'
        bne     l_ko
        lda     ustat + 1
        cmp     #'0'
        bne     l_ko
        sec
        rts
l_ko:   clc
        rts
}

        .macro setlim(v) {
        lda     #<v
        sta     ulim
        lda     #>v
        sta     ulim + 1
        }

// Ouvre une connexion TCP vers SERVER:PORT. C = 1 et A = socket, sinon C = 0. (30 s)
net_open: {
        lda     #$03
        sta     cmd
        lda     #$07
        sta     cmd + 1
        lda     #<SERVER_PORT
        sta     cmd + 2
        lda     #>SERVER_PORT
        sta     cmd + 3
        ldx     #0
l:      lda     host,x
        sta     cmd + 4,x
        beq     e
        inx
        bne     l
e:      txa
        clc
        adc     #5
        tax
        :setlim(30 * T_SEC)
        jsr     uci_exec
        bcc     ko
        lda     rep_n
        beq     ko
        lda     rep
        sec
        rts
ko:     clc
        rts
}

// Lecture non bloquante du socket A : 120 octets au plus, laissés dans rep + 2 (RDATA). C = 0 : A = nombre lu (0 = rien pour l'instant) ;
// C = 1 : connexion fermée ou Ultimate muet (ne plus toucher au socket). (3 s)
net_read: {
        sta     cmd + 2
        lda     #$03
        sta     cmd
        lda     #$10
        sta     cmd + 1
        lda     #120
        sta     cmd + 3
        lda     #0
        sta     cmd + 4
        ldx     #5
        :setlim(3 * T_SEC)
        jsr     uci_exec
        bcs     l_ok
        lda     uci_bloquee
        bne     l_dead
l_ok:   lda     rep_n                   // 2 octets de longueur (petit-boutiste, $FFFF = rien) puis les données
        cmp     #2
        bcc     l_none
        lda     rep + 1
        bne     l_none                  // > 255 ou $FFFF
        lda     rep
        beq     l_none
        cmp     #121
        bcs     l_zero
        sta     un
        clc
        adc     #2
        cmp     rep_n                   // longueur annoncée > reçue : on ignore
        beq     l_cp
        bcs     l_zero
l_cp:   lda     un
        clc
        rts
// sans données, le statut dit pourquoi : « 02,NO DATA: 11 » (EAGAIN) sur une connexion vivante, autre chose si fermée
l_none: ldx     #0
l_s:    lda     ustat,x
        beq     l_dead
        cmp     #':'
        bne     l_n
        lda     ustat + 1,x
        cmp     #' '
        bne     l_n
        lda     ustat + 2,x
        cmp     #'1'
        bne     l_n
        lda     ustat + 3,x
        cmp     #'1'
        beq     l_zero
l_n:    inx
        cpx     #STAT_MAX
        bne     l_s
l_dead: sec
        rts
l_zero: lda     #0
        clc
        rts
}

// Écrit X octets de WDATA (= cmd + 3, où l'appelant les a préparés) sur le socket A. C = 1 si accepté. (3 s)
net_write: {
        sta     cmd + 2
        txa
        tax
        lda     #$03
        sta     cmd
        lda     #$11
        sta     cmd + 1
        txa
        clc
        adc     #3
        tax
        :setlim(3 * T_SEC)
        jmp     uci_exec
}

// Ferme le socket A. (3 s)
net_close: {
        sta     cmd + 2
        lda     #$03
        sta     cmd
        lda     #$09
        sta     cmd + 1
        ldx     #3
        :setlim(3 * T_SEC)
        jmp     uci_exec
}

host:   .encoding "ascii"
        .text SERVER_HOST
        .byte 0
