; Lanceur : le PRG est chargé à $0801 ; ce code (appelé par le SYS de l'en-tête BASIC)
; recopie l'image du programme à $C000 puis y saute.
        .import __LOADIMG_START__, __ONCE_LOAD__, __ONCE_SIZE__, __HI_START__

        .segment "BOOT"
        sei
        lda     #<__LOADIMG_START__
        sta     $FB
        lda     #>__LOADIMG_START__
        sta     $FC
        lda     #<__HI_START__
        sta     $FD
        lda     #>__HI_START__
        sta     $FE
        ldx     #>(__ONCE_LOAD__ + __ONCE_SIZE__ - __LOADIMG_START__) + 1   ; nombre de pages
        ldy     #0
@copie: lda     ($FB),y
        sta     ($FD),y
        iny
        bne     @copie
        inc     $FC
        inc     $FE
        dex
        bne     @copie
        lda     #$36            ; ROM du BASIC coupée : $A000-$BFFF devient de la RAM
        sta     $01             ; (sinon le saut en $B8xx exécuterait la ROM)
        cli
        jmp     __HI_START__
