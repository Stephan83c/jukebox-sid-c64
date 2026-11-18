; Replace la pile C (cc65) en haut de la mémoire.
;
; Le démarrage de cc65 place le sommet de la pile à __MAIN_START__ + __MAIN_SIZE__, c'est-à-dire ici
; $080D + $40 = $084D (le lanceur BASIC) : la pile descendait dans la zone où se chargent les morceaux et
; écrasait leurs premiers octets ($082D-$0847). Les morceaux chargés à $0800 dont le code d'initialisation
; s'y trouvait (Alright, Dark Ages...) plantaient. La zone $CE00-$CFFF est réservée à la pile (voir
; jukebox.cfg : __STACKSIZE__), elle descend donc de __HIMEM__ ($D000).
;
; Constructeur : exécuté par initlib, après la mise en place de la pile par cc65 et avant main().
        .export         stack_haut
        .constructor    stack_haut
        .importzp       sp
        .import         __HIMEM__

        .segment "ONCE"
stack_haut:
        lda     #<__HIMEM__
        sta     sp
        lda     #>__HIMEM__
        sta     sp + 1
        rts
