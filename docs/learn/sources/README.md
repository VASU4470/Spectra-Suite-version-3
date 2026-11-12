# Measured example sources

## Polystyrene transmission FT-IR

Fabio Corradini, *uFTIR*, original polystyrene-sheet reference measurement.
The acquisition notes are in the [upstream data README](https://github.com/fcorra/uFTIR/blob/master/data-raw/README.md).
The bundled `dump_refs.Rdata` is the upstream reference archive (Git blob
`64cddb052ef8eb1c0edbc1af4db503f030b40711`). It contains the original `wn`
and `ps` vectors used here. SpectraSuite paired these vectors, converted
absorbance A to percent transmittance using 100 × 10⁻ᴬ, and formatted the
values as CSV. All 572 points were retained. The reference figure was
rendered from that CSV. The upstream package declares GPL-3. See
[GPL-3.0.txt](GPL-3.0.txt) for the license accompanying the source and its
derived example data.

## LaB₆ reference powder XRD

Advanced Photon Source, *GSAS-II Tutorials*, [Create Instrument Parameter
File](https://advancedphotonsource.github.io/GSAS-II-tutorials/CWInstDemo/FindProfParamCW.html),
wider-range NIST SRM 660c pattern. The source is `NIST660CBI.gsas` from
the upstream tutorial repository, bundled as `NIST660CBI.gsas.gz`. SpectraSuite unpacked the GSAS STD
intensities and calculated 2θ in degrees as
`(1500.66 + index × 1.31303) / 100`, starting at index zero. All 8,378
intensity values were retained. The reference figure was rendered from
that CSV. See the bundled [upstream notice](GSAS-II-LICENSE.txt).
