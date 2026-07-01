// satellite.js v7's package root also exports its optional WASM bulk propagator.
// Import the small JavaScript SGP4 modules directly so the browser bundle does
// not pull in a Node-oriented pthread worker that this application never uses.
export { json2satrec } from "../../node_modules/satellite.js/dist/io.js";
export { gstime, propagate } from "../../node_modules/satellite.js/dist/propagation.js";
export {
  degreesLat,
  degreesLong,
  ecfToLookAngles,
  eciToEcf,
  eciToGeodetic,
  radiansLat,
  radiansLong,
} from "../../node_modules/satellite.js/dist/transforms.js";
export type { OMMJsonObject } from "../../node_modules/satellite.js/dist/common-types.js";
export type { SatRec } from "../../node_modules/satellite.js/dist/propagation/SatRec.js";
