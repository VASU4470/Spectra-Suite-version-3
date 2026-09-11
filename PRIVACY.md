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
updates**. Manual checks remain available from **Help → Check for Updates**.
The application and all scientific tools continue to work without internet.

Version 3.1.0 contains no user login, license activation, advertising, or usage
analytics.

