import AppKit
import Foundation
import SwiftUI

private struct ConfirmationInput: Decodable {
    let recipient: String
    let text: String
    let files: [String]
    let canSuppress: Bool
}

private struct ConfirmationOutput: Encodable {
    let decision: String
    let suppress: Bool
}

private final class ConfirmationPanel: NSPanel {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { true }
}

private let messageGradient = LinearGradient(
    colors: [
        Color(red: 0.12, green: 0.54, blue: 1.0),
        Color(red: 0.04, green: 0.44, blue: 0.98),
    ],
    startPoint: .top,
    endPoint: .bottom
)

private struct ConfirmationView: View {
    let input: ConfirmationInput
    let icon: NSImage
    let cursorIcon: NSImage?
    let onDecision: (Bool, Bool) -> Void

    private var visibleFiles: [String] {
        input.files.prefix(3).map { URL(fileURLWithPath: $0).lastPathComponent }
    }

    private var initials: String? {
        let letters = input.recipient
            .split(whereSeparator: { $0.isWhitespace })
            .prefix(2)
            .compactMap { word in word.first(where: \.isLetter) }
        return letters.isEmpty ? nil : letters.map(String.init).joined().uppercased()
    }

    private var contactBadge: some View {
        ZStack {
            Circle()
                .fill(
                    LinearGradient(
                        colors: [
                            Color(red: 0.66, green: 0.76, blue: 0.91),
                            Color(red: 0.48, green: 0.56, blue: 0.77),
                        ],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )
            if let initials {
                Text(initials)
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(.white)
            } else {
                VStack(spacing: 1) {
                    Circle()
                        .fill(.white)
                        .frame(width: 8, height: 8)
                    Ellipse()
                        .fill(.white)
                        .frame(width: 17, height: 9)
                }
                .offset(y: 1)
            }
        }
        .frame(width: 28, height: 28)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 10) {
                HStack(spacing: 5) {
                    Image(nsImage: icon)
                        .resizable()
                        .frame(width: 28, height: 28)
                    if let cursorIcon {
                        Image(nsImage: cursorIcon)
                            .resizable()
                            .frame(width: 24, height: 24)
                    }
                }
                VStack(alignment: .leading, spacing: 1) {
                    Text("Send a message?")
                        .font(.system(size: 15, weight: .semibold))
                    Text("Messages for Cursor")
                        .font(.system(size: 11))
                        .foregroundStyle(.secondary)
                }
                Spacer()
            }
            .padding(.bottom, 5)

            HStack(spacing: 8) {
                contactBadge
                HStack(spacing: 4) {
                    Text("To:")
                        .foregroundStyle(.secondary)
                    Text(input.recipient)
                        .fontWeight(.medium)
                        .lineLimit(1)
                }
                .font(.system(size: 12))
                Spacer()
            }

            HStack(alignment: .bottom) {
                Spacer(minLength: 48)
                VStack(alignment: .leading, spacing: 6) {
                    if !input.text.isEmpty {
                        Text(input.text)
                            .font(.system(size: 13.5))
                            .lineSpacing(2)
                            .foregroundStyle(.white)
                            .lineLimit(6)
                            .fixedSize(horizontal: false, vertical: true)
                            .textSelection(.enabled)
                    }
                    ForEach(visibleFiles, id: \.self) { filename in
                        HStack(spacing: 4) {
                            Image(systemName: "paperclip")
                                .font(.system(size: 10))
                            Text(filename)
                                .font(.system(size: 11, weight: .medium))
                                .lineLimit(1)
                        }
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .background(Color.white.opacity(0.2))
                        .clipShape(Capsule())
                        .foregroundStyle(.white)
                    }
                    if input.files.count > visibleFiles.count {
                        Text("+\(input.files.count - visibleFiles.count) more")
                            .font(.system(size: 11))
                            .foregroundStyle(.white.opacity(0.8))
                    }
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(messageGradient)
                .clipShape(
                    UnevenRoundedRectangle(
                        topLeadingRadius: 16,
                        bottomLeadingRadius: 16,
                        bottomTrailingRadius: 4,
                        topTrailingRadius: 16,
                        style: .continuous
                    )
                )
                .frame(maxWidth: 270, alignment: .trailing)
            }
            .frame(maxWidth: .infinity, alignment: .trailing)

            if input.canSuppress {
                Text("“Always Send” bypasses confirmation for the current agent only.")
                    .font(.system(size: 10.5))
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .trailing)
            }

            HStack(spacing: 8) {
                Spacer()
                Button("Skip") {
                    onDecision(false, false)
                }
                    .buttonStyle(.bordered)
                    .buttonBorderShape(.roundedRectangle(radius: 7))
                    .keyboardShortcut(.cancelAction)
                    .controlSize(.regular)
                    .font(.system(size: 12))
                if input.canSuppress {
                    Button("Always Send") {
                        onDecision(true, true)
                    }
                        .buttonStyle(.bordered)
                        .buttonBorderShape(.roundedRectangle(radius: 7))
                        .controlSize(.regular)
                        .font(.system(size: 12))
                }
                Button("Send") {
                    onDecision(true, false)
                }
                    .buttonStyle(.borderedProminent)
                    .buttonBorderShape(.roundedRectangle(radius: 7))
                    .keyboardShortcut(.defaultAction)
                    .controlSize(.regular)
                    .font(.system(size: 12, weight: .medium))
            }
            .padding(.top, 2)
        }
        .padding(16)
        .frame(width: 360)
        .background(Color(nsColor: .windowBackgroundColor))
    }
}

do {
    let input = try JSONDecoder().decode(
        ConfirmationInput.self,
        from: FileHandle.standardInput.readDataToEndOfFile()
    )

    let messagesPath = "/System/Applications/Messages.app"
    let icon = NSWorkspace.shared.icon(forFile: messagesPath)
    let cursorURL = NSWorkspace.shared.urlForApplication(
        withBundleIdentifier: "com.todesktop.230313mzl4w4u92"
    )
    let cursorLogoURL = cursorURL?.appendingPathComponent(
        "Contents/Resources/app/out/vs/workbench/contrib/onboarding/electron-sandbox/media/logo.svg"
    )
    let cursorIcon = cursorLogoURL.flatMap { NSImage(contentsOf: $0) }
        ?? cursorURL.map { NSWorkspace.shared.icon(forFile: $0.path) }
    let app = NSApplication.shared
    app.setActivationPolicy(.regular)
    app.applicationIconImage = icon
    app.finishLaunching()

    var shouldSend = false
    var suppress = false
    let view = ConfirmationView(input: input, icon: icon, cursorIcon: cursorIcon) { send, shouldSuppress in
        shouldSend = send
        suppress = shouldSuppress
        app.stopModal()
    }
    let hostingView = NSHostingView(rootView: view)
    let fittingSize = hostingView.fittingSize
    hostingView.frame = NSRect(x: 0, y: 0, width: 360, height: fittingSize.height)

    let panel = ConfirmationPanel(
        contentRect: hostingView.frame,
        styleMask: [.borderless],
        backing: .buffered,
        defer: false
    )
    panel.title = "Messages for Cursor"
    panel.isMovableByWindowBackground = true
    panel.isReleasedWhenClosed = false
    panel.hidesOnDeactivate = false
    panel.isOpaque = false
    panel.backgroundColor = .clear
    panel.hasShadow = true
    panel.level = .modalPanel
    panel.collectionBehavior = [.moveToActiveSpace, .transient]
    panel.contentView = hostingView
    hostingView.wantsLayer = true
    hostingView.layer?.cornerRadius = 16
    hostingView.layer?.cornerCurve = .continuous
    hostingView.layer?.masksToBounds = true
    panel.center()

    NSRunningApplication.current.unhide()
    NSRunningApplication.current.activate(options: [.activateAllWindows])
    panel.makeKeyAndOrderFront(nil)
    panel.orderFrontRegardless()
    panel.makeKey()
    app.runModal(for: panel)
    panel.orderOut(nil)

    let output = ConfirmationOutput(
        decision: shouldSend ? "send" : "skip",
        suppress: shouldSend && suppress
    )
    let data = try JSONEncoder().encode(output)
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write(Data([0x0A]))
} catch {
    FileHandle.standardError.write(Data("messages confirmation: \(error)\n".utf8))
    exit(1)
}
