// Page zéro du client (zone du BASIC, inutilisée : le BASIC ne tourne plus ; le lecteur sauve et restaure toute la page)
        .const p0 = $02                 // pointeur de texte
        .const p1 = $04                 // pointeur d'analyse (en-tête)
        .const p3 = $06                 // case écran
        .const dst = $08                // destination des octets reçus
        .const hp = $0A                 // écriture dans l'en-tête
        .const sp_ = $0C                // texte en ligne (say)
        .const q = $0E                  // début du champ courant
        .const num = $10                // nombre lu (2 octets)
        .const rem = $12                // octets restant à recevoir dans la phase (2 octets)
        .const cx = $14
        .const cy = $15
        .const col = $16
        .const ysave = $17
        .const ttmp = $18

