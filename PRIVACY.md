# SpectraSuite privacy

SpectraSuite performs scientific processing locally. Imported spectra, edited
tables, annotations, analysis results, and exports are not uploaded by the
application.

By default, the launcher checks the public GitHub Releases API at most once per
24 hours so it can notify the user about a newer version. This request contains
the normal network information needed for an HTTPS request and a user-agent
containing the application version. SpectraSuite does not attach a unique
installation identifier, account, filename, spectrum, or analysis result.

Automatic checks can be disabled from **Help → Automatically check for
updates** or **Account → Privacy & update preferences**. Manual checks remain
available from **Help → Check for Updates** and the same preferences dialog.
When an update is found, a non-blocking in-window banner links to its GitHub
release page. A failed automatic check is retried quietly while the application
remains open. The application and all scientific tools continue to work without
internet.

Version 3.2.0 contains no user login, license activation, advertising, or usage
analytics.

## Optional email updates

Choosing **Account → Get update emails** opens a public Brevo subscription
form in the user's normal web browser. SpectraSuite does not open this page
automatically and does not send an email address, installation identifier,
filename, spectrum, or analysis result to the form. If the user voluntarily
submits the external form, Brevo processes the submitted email address and
consent for SpectraSuite release, security, and feature-update messages. Email campaigns must include an unsubscribe mechanism; the publisher must
verify the hosted form's consent and double-opt-in settings before sending. Declining or cancelling a
subscription has no effect on application features or offline use.
