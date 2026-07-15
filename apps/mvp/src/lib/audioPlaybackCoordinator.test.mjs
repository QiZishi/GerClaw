import assert from "node:assert/strict";
import test from "node:test";
import {
  claimActiveAudioPlayer,
  releaseActiveAudioPlayer,
  stopActiveAudioPlayer,
} from "./audioPlaybackCoordinator.ts";

test("only the current audio player receives a global stop request", () => {
  stopActiveAudioPlayer();
  const first = Symbol("first");
  const second = Symbol("second");
  let firstStops = 0;
  let secondStops = 0;

  claimActiveAudioPlayer(first, () => {
    firstStops += 1;
    releaseActiveAudioPlayer(first);
  });
  claimActiveAudioPlayer(second, () => {
    secondStops += 1;
    releaseActiveAudioPlayer(second);
  });

  assert.equal(firstStops, 1, "starting another response stops the earlier response");
  assert.equal(secondStops, 0);

  stopActiveAudioPlayer();
  assert.equal(secondStops, 1, "workflow exit stops the response that is actually playing");
  stopActiveAudioPlayer();
  assert.equal(secondStops, 1, "a completed stop is idempotent");
});
