"""Planning a highlight edit.

The rendering path needs real video and a GPU, so it is exercised manually. These
cover the decision logic, which is where mistakes would silently produce a bad
edit rather than an error.
"""

import pytest

from ytupload.editor import (
    LEAD_IN,
    MIN_SEGMENT,
    PREGAME_SECONDS,
    Analysis,
    _segments_above,
    _smooth,
    describe,
    plan,
    relative_loudness,
    spread_activity,
)


# ------------------------------------------------------------------ smoothing


def test_smoothing_flattens_a_spike():
    values = [0, 0, 0, 10, 0, 0, 0]
    smoothed = _smooth(values, 1)
    assert smoothed[3] < 10
    assert smoothed[2] > 0  # the spike bleeds into its neighbours


def test_smoothing_preserves_length():
    assert len(_smooth([1.0] * 50, 5)) == 50


def test_smoothing_a_constant_signal_changes_nothing():
    assert _smooth([3.0] * 20, 4) == pytest.approx([3.0] * 20)


# ----------------------------------------------------------- relative loudness


def test_a_constant_signal_has_no_relative_loudness():
    """Absolute level is uninformative; only deviation from the baseline counts."""
    assert relative_loudness([60.0] * 300) == pytest.approx([0.0] * 300, abs=1e-6)


def test_a_burst_rises_above_its_own_baseline():
    levels = [50.0] * 300
    for i in range(140, 160):
        levels[i] = 80.0
    relative = relative_loudness(levels)
    assert relative[150] > 5
    assert relative[10] < 1


def test_a_loud_recording_is_not_inherently_interesting():
    """A quiet burst in a quiet video should beat steady loudness in a loud one."""
    quiet = [40.0] * 300
    for i in range(140, 160):
        quiet[i] = 60.0
    loud = [85.0] * 300
    assert max(relative_loudness(quiet)) > max(relative_loudness(loud))


# -------------------------------------------------------------------- spreading


def test_activity_spreads_around_a_spike():
    activity = [0.0] * 60
    activity[30] = 2.0
    spread = spread_activity(activity)
    assert spread[30] == pytest.approx(2.0)
    assert spread[25] > 0   # run-up before the event is kept
    assert spread[34] > 0   # and the aftermath


def test_spreading_reaches_further_back_than_forward():
    """A fight has a run-up; the interesting part starts before the kill lands."""
    activity = [0.0] * 60
    activity[30] = 2.0
    spread = spread_activity(activity)
    assert spread[30 - 12] > 0
    assert spread[30 + 12] == 0


def test_spreading_an_empty_signal_is_empty():
    assert spread_activity([0.0] * 40) == [0.0] * 40


# ------------------------------------------------------------------ thresholds


def _curve(length, peaks):
    values = [0.0] * length
    for position, height in peaks:
        values[position] = height
    return values


def test_only_peaks_above_the_threshold_survive():
    interest = _curve(600, [(100, 5.0), (300, 1.0)])
    segments = _segments_above(interest, 3.0, 0, 600)
    assert len(segments) == 1
    assert segments[0][0] < 100 < segments[0][1]


def test_segments_shorter_than_the_minimum_are_dropped():
    interest = _curve(600, [(100, 5.0)])
    long_enough = _segments_above(interest, 3.0, 0, 600)
    assert all(b - a >= MIN_SEGMENT for a, b in long_enough)


def test_nearby_peaks_merge_into_one_segment():
    """Two kills seconds apart are one moment, not two cuts."""
    interest = _curve(600, [(200, 5.0), (203, 5.0)])
    segments = _segments_above(interest, 3.0, 0, 600)
    assert len(segments) == 1


def test_distant_peaks_stay_separate():
    interest = _curve(600, [(100, 5.0), (400, 5.0)])
    assert len(_segments_above(interest, 3.0, 0, 600)) == 2


def test_segments_never_leave_the_requested_range():
    interest = _curve(600, [(310, 5.0)])
    for a, b in _segments_above(interest, 3.0, 300, 500):
        assert a >= 300 and b <= 500


# ----------------------------------------------------------------------- plan


def _analysis(duration=2400.0, game_start=100.0, peaks=()):
    return Analysis(
        duration=duration,
        game_start=game_start,
        interest=_curve(int(duration), list(peaks)),
    )


def test_laning_is_always_the_first_segment():
    analysis = _analysis(peaks=[(1500, 8.0)])
    segments = plan(analysis, target_minutes=25, lane_minutes=10)
    start, end = segments[0]
    assert start == pytest.approx(analysis.game_start - LEAD_IN)
    assert end == pytest.approx(analysis.game_start + 600)


def test_a_lead_in_before_the_horn_is_kept():
    segments = plan(_analysis(), target_minutes=25, lane_minutes=10)
    assert segments[0][0] < 100.0


def test_total_runtime_respects_the_target():
    peaks = [(t, 8.0) for t in range(800, 2300, 60)]
    segments = plan(_analysis(peaks=peaks), target_minutes=25, lane_minutes=10)
    total = sum(b - a for a, b in segments)
    assert total <= 25 * 60 + 30  # bisection lands just under, never far over


def test_a_shorter_target_keeps_less_when_there_is_more_than_it_can_fit():
    # Spaced far enough apart to stay separate scenes under the padding, with
    # varied heights so the threshold has something to discriminate on, and
    # enough of them that the smaller budget genuinely cannot hold them all.
    peaks = [(t, 1.0 + (t % 7)) for t in range(760, 2340, 100)]
    analysis = _analysis(peaks=peaks)
    short = sum(b - a for a, b in plan(analysis, target_minutes=18, lane_minutes=10))
    long = sum(b - a for a, b in plan(analysis, target_minutes=30, lane_minutes=10))
    assert short < long


def test_the_target_is_a_cap_not_a_quota():
    """With little of interest, keep only what is interesting - never pad to length.

    A sparse match should produce a short video, not a long one bulked out with
    farming to hit the requested runtime.
    """
    peaks = [(t, 8.0) for t in range(800, 2300, 200)]
    analysis = _analysis(peaks=peaks)
    modest = plan(analysis, target_minutes=18, lane_minutes=10)
    generous = plan(analysis, target_minutes=40, lane_minutes=10)
    assert sum(b - a for a, b in modest) == sum(b - a for a, b in generous)
    assert sum(b - a for a, b in generous) < 40 * 60


def test_more_laning_leaves_less_for_highlights():
    peaks = [(t, 8.0) for t in range(700, 2300, 100)]
    analysis = _analysis(peaks=peaks)
    few = plan(analysis, target_minutes=25, lane_minutes=8)
    many = plan(analysis, target_minutes=25, lane_minutes=15)
    assert (many[0][1] - many[0][0]) > (few[0][1] - few[0][0])
    assert len(many) < len(few)


def test_laning_longer_than_the_target_is_truncated_not_overrun():
    analysis = _analysis(duration=2400.0, game_start=100.0)
    segments = plan(analysis, target_minutes=5, lane_minutes=10)
    total = sum(b - a for a, b in segments)
    assert total <= 5 * 60 + 1


def test_the_post_game_tail_is_dropped():
    """The closing seconds are scoreboards and reward screens, not play."""
    peaks = [(2390, 9.0)]
    segments = plan(_analysis(duration=2400.0, peaks=peaks), tail_trim=40)
    assert all(b <= 2400 - 40 + 1 for a, b in segments)


def test_a_match_with_no_events_still_returns_the_laning_phase():
    segments = plan(_analysis(peaks=[]), target_minutes=25, lane_minutes=10)
    assert len(segments) >= 1
    assert segments[0][1] > segments[0][0]


def test_segments_are_in_chronological_order():
    peaks = [(t, 8.0) for t in range(800, 2300, 120)]
    segments = plan(_analysis(peaks=peaks))
    assert segments == sorted(segments)


def test_segments_do_not_overlap():
    peaks = [(t, 8.0) for t in range(800, 2300, 40)]
    segments = plan(_analysis(peaks=peaks))
    for earlier, later in zip(segments, segments[1:]):
        assert earlier[1] <= later[0]


# ------------------------------------------------------------------- describe


def test_describe_renders_timestamps_and_a_total():
    text = describe([(0.0, 90.0), (120.0, 185.0)])
    assert "0:00 - 1:30" in text
    assert "2:00 - 3:05" in text
    assert "total:" in text
    assert "2 segments" in text


def test_pregame_constant_matches_dota():
    """Dota counts down 90s between the HUD appearing and creeps spawning."""
    assert PREGAME_SECONDS == 90.0


def test_the_target_is_never_exceeded_when_nothing_fits():
    """With a budget too small for any highlight, keep laning only - not everything.

    Regression: the bisection ceiling used to sit *at* max(interest), and the
    comparison is inclusive, so the returned threshold could be one that
    overshot the budget.
    """
    peaks = [(t, 8.0) for t in range(800, 2300, 60)]
    analysis = _analysis(peaks=peaks)
    segments = plan(analysis, target_minutes=11, lane_minutes=10)
    total = sum(b - a for a, b in segments)
    assert total <= 11 * 60 + 1
    assert len(segments) == 1  # laning only


def test_a_bitrate_ceiling_exists_and_is_sane():
    """Without a cap, NVENC spent MORE bits than the source, so the cut was
    barely smaller than the original. 24 Mbps is YouTube's 1440p60 guidance."""
    from ytupload.editor import MAX_BITRATE_MBPS

    assert 10 <= MAX_BITRATE_MBPS <= 30


def test_extract_reuses_a_locked_workdir(tmp_path, monkeypatch):
    """Windows rmtree fails with WinError 145 while any handle is open.

    Regression: that crashed the whole analysis. Extraction must tolerate a
    workdir it cannot delete, while still clearing stale frames so they do not
    pollute the new run.
    """
    from types import SimpleNamespace

    from ytupload import editor

    workdir = tmp_path / "strip"
    workdir.mkdir()
    (workdir / "999.jpg").write_bytes(b"stale frame from a previous run")

    def refuse(path, ignore_errors=False, **kwargs):
        if not ignore_errors:
            raise OSError(145, "The directory is not empty")

    monkeypatch.setattr(editor.shutil, "rmtree", refuse)
    monkeypatch.setattr(editor, "find_ffmpeg", lambda: "ffmpeg-not-used")
    monkeypatch.setattr(editor, "_frame_rate", lambda *a, **k: 60.0)
    monkeypatch.setattr(
        editor.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=1, stdout=b"", stderr=b"no ffmpeg"),
    )

    with pytest.raises(editor.EditError, match="no frames"):
        editor.extract_score_strip(tmp_path / "video.mp4", workdir)

    # The stale frame must be gone, or it would be read as real data.
    assert not (workdir / "999.jpg").exists()


# --------------------------------------------------- segments carry context


def test_padding_is_generous_enough_to_show_why_a_fight_happened():
    """Regression: 6s of lead-in dropped viewers into the middle of fights.

    A teamfight's run-up - the rotation, the positioning, the ward going down -
    is most of what makes it readable, and it happens well before anyone dies.
    """
    from ytupload.editor import PAD_AFTER, PAD_BEFORE

    assert PAD_BEFORE >= 20, "too little lead-in; fights start without explanation"
    assert PAD_AFTER >= 12, "too little aftermath; the outcome gets cut away"
    assert PAD_BEFORE > PAD_AFTER, "the run-up matters more than the aftermath"


def test_no_segment_is_short_enough_to_feel_like_a_jump_cut():
    from ytupload.editor import MIN_SEGMENT

    assert MIN_SEGMENT >= 25


def test_related_action_merges_into_one_scene():
    """Two fights a minute apart are one sequence, not two abrupt cuts."""
    interest = _curve(2400, [(1000, 8.0), (1055, 8.0)])
    segments = _segments_above(interest, 3.0, 700, 2300)
    assert len(segments) == 1


def test_a_real_length_match_yields_few_long_segments_not_many_short_ones():
    """The failure mode being guarded against is a choppy edit.

    Twenty-one segments across 25 minutes is a cut every 70 seconds, which is
    what made the first edit feel abrupt.
    """
    # Real fights produce several kills within seconds; isolated evenly-spaced
    # events are not what a match looks like.
    peaks = [
        (moment + offset, 4.0 + (moment % 5))
        for moment in range(800, 2300, 200)
        for offset in (0, 8, 16)
    ]
    segments = plan(_analysis(peaks=peaks), target_minutes=25, lane_minutes=10)
    midgame = segments[1:]
    assert len(midgame) <= 12, "too many cuts; the edit will feel choppy"
    if midgame:
        average = sum(b - a for a, b in midgame) / len(midgame)
        assert average >= 45, "segments too short to establish context"

# ------------------------------------------------- channel upload limits


def test_eligible_is_not_allowed():
    """Regression: a 25-minute upload was accepted and then deleted by YouTube.

    longUploadsStatus 'eligible' means the channel *could* enable long uploads,
    not that it has. Only 'allowed' accepts a video over 15 minutes.
    """
    from ytupload.uploader import UNVERIFIED_LIMIT_SECONDS, UploadError, YoutubeUploader

    class FakeChannels:
        def list(self, **kwargs):
            return self

        def execute(self):
            return {"items": [{"id": "x", "snippet": {}, "status": {"longUploadsStatus": "eligible"}}]}

    class FakeService:
        def channels(self):
            return FakeChannels()

    uploader = YoutubeUploader(service=FakeService())
    uploader.require_upload_length(UNVERIFIED_LIMIT_SECONDS - 1)  # short: fine
    with pytest.raises(UploadError, match="not 'allowed'"):
        uploader.require_upload_length(UNVERIFIED_LIMIT_SECONDS + 1)


def test_allowed_permits_a_long_upload():
    from ytupload.uploader import UNVERIFIED_LIMIT_SECONDS, YoutubeUploader

    class FakeChannels:
        def list(self, **kwargs):
            return self

        def execute(self):
            return {"items": [{"id": "x", "snippet": {}, "status": {"longUploadsStatus": "allowed"}}]}

    class FakeService:
        def channels(self):
            return FakeChannels()

    YoutubeUploader(service=FakeService()).require_upload_length(
        UNVERIFIED_LIMIT_SECONDS * 2
    )


def test_unknown_duration_does_not_block_an_upload():
    from ytupload.uploader import YoutubeUploader

    YoutubeUploader(service=object()).require_upload_length(None)


def test_chapter_marks_skip_the_run_up():
    """A chapter mark must land on the event, not on the walk up to it.

    Every scene opens with PAD_BEFORE seconds of approach. That padding makes
    the video read when watched straight through, but someone clicking a
    chapter wants the event. Marking the segment start put them 25 seconds of
    empty terrain away from what the label promised.
    """
    from ytupload.editor import PAD_BEFORE, chapters_for

    segments = [(100.0, 700.0), (800.0, 900.0)]
    marks = chapters_for(segments, game_start=100.0)
    assert marks[0][0] == 0.0, "the first mark must be 0:00 or YouTube drops them all"
    # Second scene begins at 600s into the edit; the mark sits PAD_BEFORE later.
    assert marks[1][0] == 600.0 + PAD_BEFORE


def test_a_short_scene_never_marks_past_its_middle():
    """Offsetting must not push the mark beyond the scene it belongs to."""
    from ytupload.editor import chapters_for

    segments = [(100.0, 700.0), (800.0, 830.0)]  # a 30s scene
    marks = chapters_for(segments, game_start=100.0)
    assert marks[1][0] <= 600.0 + 15.0


def test_chapter_game_clock_follows_the_offset_mark():
    """The stated game time must match where the viewer actually lands."""
    from ytupload.editor import PAD_BEFORE, chapters_for

    marks = chapters_for([(100.0, 700.0), (800.0, 900.0)], game_start=100.0)
    assert marks[1][1] == 700.0 + PAD_BEFORE
