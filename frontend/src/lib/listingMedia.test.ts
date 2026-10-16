import assert from "node:assert/strict";
import test from "node:test";
import { isPanoramaCaption, panoramaCaption, visibleCaption } from "./listingMedia.ts";

test("only an explicit 360 caption marker opens the panorama viewer", () => {
  assert.equal(isPanoramaCaption("360: Living room"), true);
  assert.equal(isPanoramaCaption("  360:"), true);
  assert.equal(isPanoramaCaption("Living room with a 360 degree mention"), false);
  assert.equal(isPanoramaCaption(""), false);
  assert.equal(isPanoramaCaption(null), false);
});

test("panorama captions keep the visible words and can be stripped", () => {
  assert.equal(panoramaCaption(""), "360:");
  assert.equal(panoramaCaption("Kitchen"), "360: Kitchen");
  assert.equal(panoramaCaption("360: Kitchen"), "360: Kitchen");
  assert.equal(visibleCaption("360: Kitchen"), "Kitchen");
  assert.equal(visibleCaption("360:"), "");
});
