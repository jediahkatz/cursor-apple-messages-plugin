import AppKit
import ApplicationServices
import CoreServices
import SQLite3
import SwiftUI

/// Display name for the menu bar and Dock. LaunchServices takes this from
/// the executable filename `bin/Messages for Cursor`.
private let appDisplayName = "Messages for Cursor"

/// The MCP server opens this window on startup, so a manual `onboard` run (or
/// an MCP restart) can otherwise stack up duplicate windows.
private enum SingleInstance {
    static let focusNotification = Notification.Name("com.cursor.messages.onboard.focus")

    /// Held for the lifetime of the process; the kernel drops it on exit.
    private static var lockFD: Int32 = -1

    /// Exits if another instance is already up, asking it to come forward.
    static func enforceOrExit() {
        let dir = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".cursor/messages")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let path = dir.appendingPathComponent("onboard.lock").path

        // If the lock is unusable, showing a second window beats showing none.
        let fd = open(path, O_CREAT | O_RDWR, 0o644)
        guard fd >= 0 else { return }

        if flock(fd, LOCK_EX | LOCK_NB) == 0 {
            lockFD = fd
            DistributedNotificationCenter.default().addObserver(
                forName: focusNotification,
                object: nil,
                queue: .main
            ) { _ in
                NSApp.activate(ignoringOtherApps: true)
                NSApp.windows.first?.makeKeyAndOrderFront(nil)
            }
            return
        }

        close(fd)
        DistributedNotificationCenter.default().postNotificationName(
            focusNotification,
            object: nil,
            userInfo: nil,
            deliverImmediately: true
        )
        exit(0)
    }
}

@main
struct OnboardApp: App {
    init() {
        SingleInstance.enforceOrExit()
        NSApplication.shared.setActivationPolicy(.regular)
        if FileManager.default.fileExists(atPath: OnboardView.messagesAppPath) {
            NSApplication.shared.applicationIconImage =
                NSWorkspace.shared.icon(forFile: OnboardView.messagesAppPath)
        }
    }

    var body: some Scene {
        WindowGroup(appDisplayName) {
            OnboardView()
                .background(Color(red: 0.95, green: 0.95, blue: 0.96))
                .onAppear {
                    NSApp.activate(ignoringOtherApps: true)
                    for window in NSApp.windows {
                        window.styleMask.remove(.resizable)
                        window.isMovableByWindowBackground = true
                        window.standardWindowButton(.zoomButton)?.isEnabled = false
                        window.standardWindowButton(.miniaturizeButton)?.isEnabled = false
                        window.center()
                    }
                }
        }
        .windowStyle(.hiddenTitleBar)
        .windowResizability(.contentSize)
        .commands { CommandGroup(replacing: .newItem) {} }
    }
}

enum PermKind: String, CaseIterable {
    case automation, contacts, disk
}

enum PermState {
    case needed, waiting, allowed
}

final class PermModel: ObservableObject {
    @Published var automation = PermState.needed
    @Published var contacts = PermState.needed
    @Published var disk = PermState.needed

    private var timer: Timer?
    /// Kinds with a native dialog still on screen. Only these keep a spinner.
    private var inFlight: Set<PermKind> = []
    private var completionScheduled = false

    init() {
        contacts = Self.permissionState()["contacts_ok"] as? Bool == true
            ? .allowed
            : .needed
        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] _ in
            self?.refresh()
        }
    }

    func state(for kind: PermKind) -> PermState {
        switch kind {
        case .automation: return automation
        case .contacts: return contacts
        case .disk: return disk
        }
    }

    /// The primary focused action: the first ungranted step.
    var primaryKind: PermKind? {
        PermKind.allCases.first { state(for: $0) != .allowed }
    }

    func refresh() {
        let diskOK = Self.chatDBReadable()
        let autoOK = Self.messagesControllable()
        DispatchQueue.main.async {
            self.apply(.automation, granted: autoOK)
            self.apply(.disk, granted: diskOK)

            if autoOK && self.contacts == .allowed && diskOK {
                Self.markComplete()
                if !self.completionScheduled {
                    self.completionScheduled = true
                    // Briefly show the final Done state before dismissing.
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) {
                        NSApp.terminate(nil)
                    }
                }
            }
        }
    }

    private func apply(_ kind: PermKind, granted: Bool) {
        if granted {
            inFlight.remove(kind)
            setState(.allowed, for: kind)
        } else if !inFlight.contains(kind) {
            // Covers "Don't Allow": the dialog is gone, so drop the spinner.
            setState(.needed, for: kind)
        }
    }

    private func setState(_ state: PermState, for kind: PermKind) {
        switch kind {
        case .automation: automation = state
        case .contacts: contacts = state
        case .disk: disk = state
        }
    }

    private func requestFinished(_ kind: PermKind) {
        inFlight.remove(kind)
        refresh()
    }

    private static var permissionsURL: URL {
        let dir = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".cursor/messages")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir.appendingPathComponent("perms.json")
    }

    private static func permissionState() -> [String: Any] {
        if let data = try? Data(contentsOf: permissionsURL),
           let parsed = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            return parsed
        }
        return [:]
    }

    private static func updatePermissionState(_ updates: [String: Any]) {
        var obj = permissionState()
        for (key, value) in updates {
            obj[key] = value
        }
        if let data = try? JSONSerialization.data(withJSONObject: obj, options: [.prettyPrinted, .sortedKeys]) {
            try? data.write(to: permissionsURL, options: .atomic)
        }
    }

    private static func markComplete() {
        var updates: [String: Any] = [:]
        updates["onboarding_complete"] = true
        updates["chat_db_ok"] = true
        updates["contacts_ok"] = true
        updates["contacts_denied"] = false
        updates["last_prompt"] = Date().timeIntervalSince1970
        updatePermissionState(updates)
    }

    func allow(_ kind: PermKind) {
        switch kind {
        case .automation:
            inFlight.insert(.automation)
            automation = .waiting
            DispatchQueue.global(qos: .userInitiated).async { [weak self] in
                let granted = Self.runAppleScript("""
                with timeout of 25 seconds
                  tell application "Messages"
                    if (count of accounts) > 0 then get id of 1st account
                  end tell
                end timeout
                """)
                DispatchQueue.main.async {
                    self?.requestFinished(.automation)
                    if !granted {
                        Self.openPrivacyPane("Privacy_Automation")
                    }
                }
            }
        case .contacts:
            let wasDenied = Self.permissionState()["contacts_denied"] as? Bool == true
            inFlight.insert(.contacts)
            contacts = .waiting
            DispatchQueue.global(qos: .userInitiated).async { [weak self] in
                let granted = Self.runAppleScript("""
                with timeout of 25 seconds
                  tell application "Contacts" to get count of people
                end timeout
                """)
                DispatchQueue.main.async {
                    self?.inFlight.remove(.contacts)
                    self?.contacts = granted ? .allowed : .needed
                    Self.updatePermissionState([
                        "contacts_ok": granted,
                        "contacts_denied": !granted,
                        "onboarding_complete": false,
                    ])
                    self?.refresh()
                    // A fresh denial returns to Allow. A subsequent attempt
                    // takes the user to the only place macOS permits recovery.
                    if !granted && wasDenied {
                        Self.openPrivacyPane("Privacy_Contacts")
                    }
                }
            }
        case .disk:
            // No dialog to await — this is granted in System Settings, and only
            // takes effect once Cursor restarts. A spinner would never resolve.
            let db = NSHomeDirectory() + "/Library/Messages/chat.db"
            _ = FileManager.default.contents(atPath: db)
            Self.openPrivacyPane("Privacy_AllFiles")
        }
    }

    private static func openPrivacyPane(_ anchor: String) {
        guard let url = URL(
            string: "x-apple.systempreferences:com.apple.preference.security?\(anchor)"
        ) else { return }
        NSWorkspace.shared.open(url)
    }

    private static func messagesControllable() -> Bool {
        canAutomate(bundleID: "com.apple.MobileSMS")
    }

    private static func canAutomate(bundleID: String) -> Bool {
        var targetDesc = AEAddressDesc()
        let bytes = Array(bundleID.utf8)
        let statusDesc = AECreateDesc(
            DescType(typeApplicationBundleID),
            bytes,
            bytes.count,
            &targetDesc
        )
        guard statusDesc == noErr else { return false }
        defer { AEDisposeDesc(&targetDesc) }
        let perm = AEDeterminePermissionToAutomateTarget(
            &targetDesc,
            DescType(typeWildCard),
            DescType(typeWildCard),
            false
        )
        return perm == noErr
    }

    @discardableResult
    private static func runAppleScript(_ source: String) -> Bool {
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
        proc.arguments = ["-"]
        let input = Pipe()
        proc.standardInput = input
        proc.standardOutput = Pipe()
        proc.standardError = Pipe()
        do {
            try proc.run()
            input.fileHandleForWriting.write(Data(source.utf8))
            input.fileHandleForWriting.closeFile()
            proc.waitUntilExit()
            return proc.terminationStatus == 0
        } catch {
            return false
        }
    }

    private static func chatDBReadable() -> Bool {
        var db: OpaquePointer?
        let uri = "file:\(NSHomeDirectory())/Library/Messages/chat.db?mode=ro"
        guard sqlite3_open_v2(uri, &db, SQLITE_OPEN_READONLY | SQLITE_OPEN_URI, nil) == SQLITE_OK else {
            sqlite3_close(db)
            return false
        }
        defer { sqlite3_close(db) }
        var stmt: OpaquePointer?
        let ok = sqlite3_prepare_v2(db, "SELECT 1", -1, &stmt, nil) == SQLITE_OK
        sqlite3_finalize(stmt)
        return ok
    }
}

struct OnboardView: View {
    static let messagesAppPath = "/System/Applications/Messages.app"
    static let cursorAppPath = "/Applications/Cursor.app"
    private static let windowWidth: CGFloat = 540
    private static let cardWidth: CGFloat = 476
    private static let cardPadding: CGFloat = 18
    private static let rowSpacing: CGFloat = 14
    private static let iconSize: CGFloat = 42
    /// Shared right-hand column, sized to the "Allow" pill so every state
    /// centers on the same axis.
    private static let actionWidth: CGFloat = 61
    static let pillHeight: CGFloat = 26
    /// Fixed so every row wraps identically; widest subtitle measures ~254pt.
    private static let textWidth: CGFloat =
        cardWidth - cardPadding * 2 - iconSize - rowSpacing * 2 - actionWidth

    @StateObject private var model = PermModel()

    var body: some View {
        VStack(spacing: 0) {
            // Header App Icons
            headerIcons
                .padding(.top, 32)
                .padding(.bottom, 16)

            // Header Title
            Text("Enable Messages for Cursor")
                .font(.system(size: 23, weight: .bold))
                .foregroundColor(Color(red: 0.12, green: 0.12, blue: 0.13))
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.bottom, 10)

            // Subtitle
            Text("Cursor needs macOS permissions to send messages, find contacts by name, and search your messages when asked.")
                .font(.system(size: 13, weight: .regular))
                .foregroundColor(Color(red: 0.44, green: 0.44, blue: 0.47))
                .multilineTextAlignment(.center)
                .lineSpacing(2.5)
                .frame(width: 396)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.bottom, 24)

            // Cards list
            VStack(spacing: 12) {
                row(
                    .automation,
                    title: "Automation",
                    subtitle: "Allows sending messages",
                    icon: AnyView(automationIcon)
                )

                row(
                    .contacts,
                    title: "Contacts",
                    subtitle: "Enables finding contacts by name",
                    icon: AnyView(appIconView("/System/Applications/Contacts.app"))
                )

                row(
                    .disk,
                    title: "Full Disk Access",
                    subtitle: "Allows searching your messages when asked",
                    icon: AnyView(diskIcon)
                )
            }
            .padding(.bottom, 32)
        }
        .frame(width: Self.windowWidth)
        .fixedSize()
    }

    private func row(_ kind: PermKind, title: String, subtitle: String, icon: AnyView) -> some View {
        HStack(spacing: Self.rowSpacing) {
            icon
                .frame(width: Self.iconSize, height: Self.iconSize)

            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                    .font(.system(size: 14, weight: .bold))
                    .foregroundColor(Color(red: 0.12, green: 0.12, blue: 0.14))
                Text(subtitle)
                    .font(.system(size: 12, weight: .regular))
                    .foregroundColor(Color(red: 0.46, green: 0.46, blue: 0.49))
                    .fixedSize(horizontal: false, vertical: true)
            }
            .frame(width: Self.textWidth, alignment: .leading)

            button(for: kind)
                .frame(width: Self.actionWidth, alignment: .center)
        }
        .padding(.horizontal, Self.cardPadding)
        .padding(.vertical, 14)
        .frame(width: Self.cardWidth, height: 72)
        .background(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(Color.white)
                .shadow(color: Color.black.opacity(0.04), radius: 3, x: 0, y: 1.5)
                .overlay(
                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                        .stroke(Color.black.opacity(0.05), lineWidth: 0.5)
                )
        )
    }

    @ViewBuilder
    private func button(for kind: PermKind) -> some View {
        switch model.state(for: kind) {
        case .allowed:
            HStack(spacing: 5) {
                Text("Done")
                    .font(.system(size: 13, weight: .medium))
                Image(systemName: "checkmark")
                    .font(.system(size: 11, weight: .semibold))
            }
            .foregroundColor(Color(red: 0.55, green: 0.55, blue: 0.58))
            .frame(height: Self.pillHeight)
        case .waiting:
            ProgressView()
                .controlSize(.small)
                .frame(height: Self.pillHeight)
        case .needed:
            let isPrimary = (model.primaryKind == kind)
            Button(action: { model.allow(kind) }) {
                Text("Allow")
            }
            .buttonStyle(CapsuleAllowButtonStyle(isPrimary: isPrimary))
        }
    }

    private var automationIcon: some View {
        RoundedRectangle(cornerRadius: 10, style: .continuous)
            .fill(
                LinearGradient(
                    colors: [
                        Color(red: 0.62, green: 0.62, blue: 0.65),
                        Color(red: 0.54, green: 0.54, blue: 0.57)
                    ],
                    startPoint: .top,
                    endPoint: .bottom
                )
            )
            .overlay(
                Image(systemName: "gearshape.2.fill")
                    .font(.system(size: 20, weight: .semibold))
                    .foregroundColor(.white)
            )
    }

    private var diskIcon: some View {
        Image(systemName: "externaldrive.fill")
            .font(.system(size: 26, weight: .medium))
            .foregroundColor(Color(red: 0.22, green: 0.22, blue: 0.25))
    }

    /// Cursor may be installed outside /Applications, so ask LaunchServices first.
    private static var cursorIconPath: String? {
        if let url = NSWorkspace.shared.urlForApplication(
            withBundleIdentifier: "com.todesktop.230313mzl4w4u92"
        ) {
            return url.path
        }
        return FileManager.default.fileExists(atPath: cursorAppPath) ? cursorAppPath : nil
    }

    private var headerIcons: some View {
        HStack(spacing: 16) {
            appIconView(Self.messagesAppPath)
                .frame(width: 64, height: 64)
            if let cursor = Self.cursorIconPath {
                appIconView(cursor)
                    .frame(width: 64, height: 64)
            }
        }
    }

    private func appIconView(_ path: String) -> some View {
        Image(nsImage: NSWorkspace.shared.icon(forFile: path))
            .resizable()
            .aspectRatio(contentMode: .fit)
    }
}

struct CapsuleAllowButtonStyle: ButtonStyle {
    var isPrimary: Bool

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13, weight: .semibold))
            .foregroundColor(isPrimary ? Color.white : Color(red: 0.18, green: 0.18, blue: 0.20))
            .padding(.horizontal, 13)
            .frame(height: OnboardView.pillHeight)
            .background(
                Capsule(style: .continuous)
                    .fill(
                        isPrimary
                            ? Color(red: 0.0, green: 0.478, blue: 1.0)
                            : Color(red: 0.90, green: 0.90, blue: 0.92)
                    )
            )
            .opacity(configuration.isPressed ? 0.75 : 1.0)
            .animation(.easeInOut(duration: 0.12), value: configuration.isPressed)
    }
}
