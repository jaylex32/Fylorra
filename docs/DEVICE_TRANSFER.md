# Device Transfer

Device Transfer sends files directly between two Fylorra instances.

## Supported Connection Modes

- Same local network: start receiving on one PC, then pick that PC from Discovered Devices on the sender.
- VPN or private tunnel: enter the receiving device VPN hostname/IP, port, and access code.
- Port forwarding: enter the public address and forwarded port for the receiving device.

Fylorra does not require a cloud account for direct transfers. Discovery only advertises device name, platform, and address. The access code is never broadcast and is required for every upload.

## Basic Flow

1. On the receiving PC, open Device Transfer and click Start Receiving.
2. Share the shown address and access code with the sender.
3. On the sending PC, select the discovered device or enter address and port manually.
4. Paste the receiver access code.
5. Add files or folders and click Send.

Received files are written to the configured inbox folder. If a file already exists, Fylorra keeps both files by adding a number to the new filename.

## Safety Behavior

- Uploads are saved as temporary `.part` files and only renamed after all bytes arrive.
- Received paths are sanitized so a sender cannot write outside the inbox.
- Existing files are not overwritten.
- Active browser download artifacts such as `.crdownload`, `.download`, `.part`, and fresh `.tmp` files are skipped by the sender by default.
- The receiver never executes received files.

## Remote Transfers

For transfers outside the local network, the receiving PC must be reachable from the sender. Use a VPN, private tunnel, or router port forwarding. A future hosted relay can be added without replacing the current UI because the transfer engine already separates device discovery from upload transport.

