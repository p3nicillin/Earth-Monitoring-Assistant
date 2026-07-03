"""Autonomous archiving of live public space imagery.

The harvester periodically pulls the latest frames from keyless NASA/NOAA/ESA
endpoints (SDO, SOHO/LASCO, GOES SUVI, DSCOVR EPIC), deduplicates by content
hash, stores frames on local disk with provenance rows in the database, and
prunes each source to a bounded archive. Over time this builds a locally
owned, browsable record of the Sun and Earth that upstream endpoints
themselves do not retain at "latest frame" URLs.
"""
