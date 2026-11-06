// La pastille d'Atlas : un orbe rond qui scintille, comme celui de Siri, montre qu'Atlas écoute, réfléchit ou parle
// quand sa fenêtre n'est pas devant la personne. Sa couleur change avec l'état, sa taille et son éclat suivent la voix.
// En option, une bulle à côté montre la demande comprise et la réponse qui s'écrit. Elle ne prend jamais le focus, se
// voit sur tous les bureaux, et disparaît en veille. Un clic coupe la voix d'Atlas ; sinon, il rouvre sa fenêtre.
//
// Lancée par le cœur comme une sortie, elle ne parle qu'avec lui, par son entrée et sa sortie (voir `CONTRAT.md`). Sa
// fiche demande à voir l'état (`{"etat": {"etat", "niveau", "fenetre"}}`, poussé à chaque changement) et chaque demande
// (`{"demande"}`) ; elle reçoit aussi chaque phrase de la réponse (`{"phrase"}`). Un clic écrit `{"geste": "couper"}` ou
// `{"geste": "montrer"}`, que sa fiche déclare. Elle s'arrête quand son entrée se ferme.

import AppKit

let env = ProcessInfo.processInfo.environment
let place = env["ATLAS_REGLAGE_PLACE"] ?? "haut-droite"
let transcription = (env["ATLAS_REGLAGE_TRANSCRIPTION"] ?? "oui") != "non"

func rvb(_ hexa: UInt32) -> SIMD3<Double> {
    SIMD3(Double((hexa >> 16) & 0xff) / 255, Double((hexa >> 8) & 0xff) / 255, Double(hexa & 0xff) / 255)
}

/// Trois teintes par état : elles tournent dans l'orbe et se mêlent.
func teintes(_ etat: String) -> [SIMD3<Double>] {
    switch etat {
    case "ecoute": return [rvb(0x5ee7ff), rvb(0x3b82f6), rvb(0x8b5cf6)]     // bleu vif : il t'écoute
    case "reflexion": return [rvb(0xc084fc), rvb(0xec4899), rvb(0x6366f1)]  // violet et rose : il réfléchit
    case "erreur": return [rvb(0xff6b6b), rvb(0xb91c1c), rvb(0xff9f9f)]
    default: return [rvb(0xf5d08a), rvb(0xf59e0b), rvb(0xfb7185)]          // or d'Atlas : il parle
    }
}

func couleur(_ c: SIMD3<Double>, _ alpha: Double) -> CGColor {
    CGColor(srgbRed: c.x, green: c.y, blue: c.z, alpha: alpha)
}

struct Etat: Equatable {
    var etat = "veille"
    var niveau = 0.0
    var fenetre = true // tant qu'on ne sait rien, on suppose la fenêtre devant : rien ne s'affiche

    var actif: Bool { ["ecoute", "reflexion", "parole", "erreur"].contains(etat) }
}

// MARK: - L'orbe

final class Orbe: NSView {
    var etat = "ecoute"
    var niveau = 0.0 // ce que dit le cœur : la voix entendue (écoute), ou celle d'Atlas (parole) si sa voix le donne
    private var niveauConnu = false // la voix d'Atlas a donné son niveau pendant cette parole
    private var lisse = 0.0
    private var t = 0.0
    private var couleurs = teintes("ecoute")

    override var isFlipped: Bool { true }

    func avancer(_ dt: Double) {
        t += dt
        // la voix d'Atlas bat avec son volume (Piper, Voxtral) ; sans niveau connu (`say`), elle respire ;
        // la réflexion, un battement lent
        if etat != "parole" { niveauConnu = false } else if niveau > 0 { niveauConnu = true }
        let voulu: Double
        switch etat {
        case "parole" where niveauConnu: voulu = 0.1 + 0.85 * niveau
        case "parole": voulu = 0.35 + 0.25 * sin(t * 7.3) * sin(t * 2.1) + 0.12 * sin(t * 13)
        case "reflexion": voulu = 0.15 + 0.1 * sin(t * 3)
        case "ecoute": voulu = min(1, niveau * 2.5)
        default: voulu = 0.1
        }
        lisse += (voulu - lisse) * min(1, dt * 10)
        let cible = teintes(etat)
        for i in 0..<3 { couleurs[i] += (cible[i] - couleurs[i]) * min(1, dt * 5) } // le passage d'une couleur à l'autre est doux
        needsDisplay = true
    }

    override func draw(_ dirtyRect: NSRect) {
        guard let g = NSGraphicsContext.current?.cgContext else { return }
        let c = CGPoint(x: bounds.midX, y: bounds.midY)
        let base = min(bounds.width, bounds.height) / 2 - 7 // la place du halo autour
        let r = base * (0.82 + 0.18 * lisse)
        let espace = CGColorSpace(name: CGColorSpace.sRGB)!

        // le halo : il grandit avec la voix
        g.saveGState()
        g.setShadow(offset: .zero, blur: 6 + 10 * lisse, color: couleur(couleurs[0], 0.55 + 0.35 * lisse))
        g.setFillColor(couleur(couleurs[1] * 0.35, 1))
        g.fillEllipse(in: CGRect(x: c.x - r, y: c.y - r, width: 2 * r, height: 2 * r))
        g.restoreGState()

        // trois nuées de couleur qui tournent dans la sphère, et scintillent
        g.saveGState()
        g.addEllipse(in: CGRect(x: c.x - r, y: c.y - r, width: 2 * r, height: 2 * r))
        g.clip()
        let vitesse = etat == "reflexion" ? 2.2 : 1.2 + lisse
        for i in 0..<3 {
            let k = Double(i)
            let angle = t * vitesse * (1 + 0.35 * k) + k * 2.1
            let p = CGPoint(x: c.x + r * 0.42 * cos(angle), y: c.y + r * 0.42 * sin(angle * 1.3 + k))
            let eclat = 0.7 + 0.3 * sin(t * (9 + 3 * k) + k) * (0.4 + lisse)
            let degrade = CGGradient(colorsSpace: espace, colors: [couleur(couleurs[i], eclat), couleur(couleurs[i], 0)] as CFArray, locations: [0, 1])!
            g.drawRadialGradient(degrade, startCenter: p, startRadius: 0, endCenter: p, endRadius: r * 1.15, options: [])
        }
        // un reflet en haut à gauche : la sphère prend du volume
        let reflet = CGPoint(x: c.x - r * 0.35, y: c.y - r * 0.4)
        let blanc = CGGradient(colorsSpace: espace, colors: [CGColor(gray: 1, alpha: 0.55), CGColor(gray: 1, alpha: 0)] as CFArray, locations: [0, 1])!
        g.drawRadialGradient(blanc, startCenter: reflet, startRadius: 0, endCenter: reflet, endRadius: r * 0.7, options: [])
        g.restoreGState()
    }
}

/// La surface qui reçoit le clic (l'orbe et la bulle).
final class Surface: NSView {
    var auClic: () -> Void = {}
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
    override func mouseDown(with event: NSEvent) { auClic() }
    override func resetCursorRects() { addCursorRect(bounds, cursor: .pointingHand) }
    override func hitTest(_ point: NSPoint) -> NSView? { frame.contains(point) ? self : nil } // les textes ne gardent pas le clic
}

/// Un panneau qui ne devient jamais la fenêtre active : la personne garde son focus.
final class Panneau: NSPanel {
    override var canBecomeKey: Bool { false }
    override var canBecomeMain: Bool { false }
}

// MARK: - La pastille

final class Pastille: NSObject, NSApplicationDelegate {
    let taille = transcription ? NSSize(width: 360, height: 66) : NSSize(width: 58, height: 58)
    var panneau: Panneau!
    var orbe: Orbe!
    var surface: Surface!
    let demandeVue = NSTextField(labelWithString: "")
    let reponseVue = NSTextField(wrappingLabelWithString: "")
    var etat = Etat()
    var montree = false
    var cacher: DispatchWorkItem?
    var anime: Timer?
    // ce qui s'est dit : la dernière demande et sa réponse
    var demande = ""
    var reponse = ""
    var dernierMot = Date.distantPast

    func applicationDidFinishLaunching(_ notification: Notification) {
        panneau = Panneau(contentRect: NSRect(origin: .zero, size: taille), styleMask: [.nonactivatingPanel, .borderless], backing: .buffered, defer: false)
        panneau.level = .statusBar
        panneau.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary, .ignoresCycle]
        panneau.isFloatingPanel = true
        panneau.hidesOnDeactivate = false
        panneau.becomesKeyOnlyIfNeeded = true
        panneau.backgroundColor = .clear
        panneau.isOpaque = false
        panneau.hasShadow = transcription // l'orbe seul a son halo ; l'ombre du panneau y dessinerait un carré
        panneau.alphaValue = 0

        let fond = NSVisualEffectView(frame: NSRect(origin: .zero, size: taille))
        fond.material = .hudWindow
        fond.blendingMode = .behindWindow
        fond.state = .active
        fond.appearance = NSAppearance(named: .vibrantDark)
        fond.wantsLayer = true
        fond.layer?.cornerRadius = transcription ? 18 : taille.height / 2
        fond.layer?.masksToBounds = true
        fond.layer?.borderWidth = 0.5
        fond.layer?.borderColor = NSColor(white: 1, alpha: 0.14).cgColor

        let cote: CGFloat = transcription ? 52 : 58
        orbe = Orbe(frame: NSRect(x: transcription ? 8 : 0, y: (taille.height - cote) / 2, width: cote, height: cote))
        fond.addSubview(orbe)
        if transcription {
            demandeVue.font = .systemFont(ofSize: 12, weight: .medium)
            demandeVue.textColor = NSColor(white: 1, alpha: 0.6)
            demandeVue.lineBreakMode = .byTruncatingTail
            reponseVue.font = .systemFont(ofSize: 13, weight: .regular)
            reponseVue.textColor = NSColor(white: 1, alpha: 0.95)
            reponseVue.maximumNumberOfLines = 2
            reponseVue.lineBreakMode = .byWordWrapping // sur deux lignes ; tronquer en fin de ligne la ramènerait à une seule
            reponseVue.cell?.truncatesLastVisibleLine = true
            fond.addSubview(demandeVue)
            fond.addSubview(reponseVue)
        }
        surface = Surface(frame: fond.bounds)
        surface.auClic = { [weak self] in self?.cliquer() }
        fond.addSubview(surface)
        panneau.contentView = fond

        ecouterLeCoeur()
    }

    // MARK: Ce que le cœur envoie sur l'entrée

    /// L'état, la demande et la réponse arrivent ligne par ligne ; quand l'entrée se ferme (le cœur part, ou éteint la
    /// pastille), on s'arrête avec lui.
    func ecouterLeCoeur() {
        Thread.detachNewThread {
            while let ligne = readLine(strippingNewline: true) {
                guard let donnees = ligne.data(using: .utf8),
                      let message = try? JSONSerialization.jsonObject(with: donnees) as? [String: Any] else { continue }
                DispatchQueue.main.async { self.recevoirMessage(message) }
            }
            DispatchQueue.main.async { exit(0) }
        }
    }

    func recevoirMessage(_ message: [String: Any]) {
        if let lu = message["etat"] as? [String: Any] {
            recevoir(Etat(etat: lu["etat"] as? String ?? "veille", niveau: lu["niveau"] as? Double ?? 0, fenetre: lu["fenetre"] as? Bool ?? false))
            return
        }
        if let texte = message["demande"] as? String {
            demande = texte
            reponse = ""
            dernierMot = Date()
        } else if let phrase = message["phrase"] as? String {
            reponse = reponse.isEmpty ? phrase : reponse + " " + phrase
            dernierMot = Date()
        } else {
            return
        }
        ecrire()
    }

    /// Les deux lignes de la bulle : « Toi : … », puis la réponse (sa fin, si elle est longue).
    func ecrire() {
        guard transcription else { return }
        let ligne1: String
        if !demande.isEmpty { ligne1 = "Toi : " + demande }
        else if etat.etat == "ecoute" { ligne1 = "Je t'écoute…" }
        else { ligne1 = "" }
        // la fin de la réponse, ce qui se dit maintenant : deux lignes, coupées à un mot
        var ligne2 = reponse
        if ligne2.count > 90 {
            let fin = ligne2.suffix(90)
            ligne2 = "…" + (fin.firstIndex(of: " ").map { String(fin[fin.index(after: $0)...]) } ?? String(fin))
        }
        if ligne2.isEmpty && !demande.isEmpty && etat.etat != "ecoute" { ligne2 = "…" }
        demandeVue.stringValue = ligne1
        reponseVue.stringValue = ligne2
        let x: CGFloat = 66, largeur = taille.width - x - 16
        if ligne2.isEmpty {
            demandeVue.frame = NSRect(x: x, y: (taille.height - 16) / 2, width: largeur, height: 16)
            reponseVue.frame = .zero
        } else {
            let haut = min(34, reponseVue.sizeThatFits(NSSize(width: largeur, height: 40)).height)
            let total = 16 + 2 + haut
            let bas = (taille.height - total) / 2
            reponseVue.frame = NSRect(x: x, y: bas, width: largeur, height: haut)
            demandeVue.frame = NSRect(x: x, y: bas + haut + 2, width: largeur, height: 16)
        }
    }

    // MARK: Ce qu'elle demande au cœur

    /// Un geste, sur sa sortie : le cœur ne le fait que si la fiche le déclare (`peut`).
    func geste(_ nom: String) {
        print("{\"geste\": \"\(nom)\"}")
        fflush(stdout)
    }

    func cliquer() {
        geste(etat.etat == "parole" ? "couper" : "montrer")
    }

    // MARK: Montrer, cacher

    func recevoir(_ nouveau: Etat) {
        let avant = etat.etat
        etat = nouveau
        if nouveau.actif {
            orbe.etat = nouveau.etat
            orbe.niveau = nouveau.niveau
            if avant != nouveau.etat { ecrire() }
        }
        let voulue = nouveau.actif && !nouveau.fenetre // le cœur sait si sa fenêtre est vraiment devant, sur le bureau affiché
        if voulue {
            cacher?.cancel()
            cacher = nil
            if !montree { montrer() }
        } else if montree && cacher == nil {
            // un court délai : entre l'écoute et la réflexion, l'état passe parfois un instant par la veille ;
            // une réponse affichée reste le temps de la finir des yeux
            let delai = nouveau.actif ? 0 : (transcription && !reponse.isEmpty ? 4 : 0.7) // la fenêtre revient : tout de suite
            let geste = DispatchWorkItem { [weak self] in self?.disparaitre() }
            cacher = geste
            DispatchQueue.main.asyncAfter(deadline: .now() + delai, execute: geste)
        }
    }

    func cadre() -> NSRect {
        let ecran = (NSScreen.main ?? NSScreen.screens.first)?.visibleFrame ?? .zero
        let x: CGFloat
        let y: CGFloat
        switch place {
        case "haut-centre": (x, y) = (ecran.midX - taille.width / 2, ecran.maxY - taille.height - 10)
        case "bas-droite": (x, y) = (ecran.maxX - taille.width - 16, ecran.minY + 16)
        default: (x, y) = (ecran.maxX - taille.width - 16, ecran.maxY - taille.height - 10)
        }
        return NSRect(origin: NSPoint(x: x, y: y), size: taille)
    }

    func montrer() {
        montree = true
        if Date().timeIntervalSince(dernierMot) > 8 { demande = ""; reponse = "" } // un vieil échange ne revient pas
        ecrire()
        panneau.setFrame(cadre(), display: true)
        panneau.orderFrontRegardless()
        NSAnimationContext.runAnimationGroup { $0.duration = 0.2; panneau.animator().alphaValue = 1 }
        var avant = Date()
        anime?.invalidate()
        anime = Timer.scheduledTimer(withTimeInterval: 1.0 / 60, repeats: true) { [weak self] _ in
            let maintenant = Date()
            self?.orbe.avancer(maintenant.timeIntervalSince(avant))
            avant = maintenant
        }
    }

    func disparaitre() {
        cacher = nil
        montree = false
        NSAnimationContext.runAnimationGroup({ $0.duration = 0.3; panneau.animator().alphaValue = 0 }) { [weak self] in
            guard let self, !self.montree else { return }
            self.anime?.invalidate()
            self.panneau.orderOut(nil)
        }
    }
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory) // ni Dock ni menu : la pastille n'est pas une app qu'on ouvre
let pastille = Pastille()
app.delegate = pastille
app.run()
