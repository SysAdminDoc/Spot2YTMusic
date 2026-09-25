# Desktop design review

Reference: [desktop concept](docs/marketing/concepts/desktop-redesign-v0.1.3.png)

Captured app: [dark theme](docs/screenshots/desktop.png), [light theme](docs/screenshots/desktop-light.png), and [compact window](docs/screenshots/desktop-compact.png)

Viewports: 1440 by 900 pixels for the main captures; 1080 by 700 pixels for the compact capture.

The app follows the concept's three-panel layout. Import and playlist selection sit on the left. The track list occupies the center. Recording details and review actions stay on the right. Authentication, transfer progress, and the activity log run across the bottom.

The app uses generic artwork because the search plan has no cover images. Exportify and saved-plan links are in the header so playlist choices remain visible. The captures show an idle plan with one unresolved song, so transfer is correctly disabled. At the compact size, the import and recording panels scroll to keep every control reachable while the track table and transfer panel stay in view.

No blocking layout, contrast, or control issues remain in the captured dark, light, and compact views.

final result: passed
