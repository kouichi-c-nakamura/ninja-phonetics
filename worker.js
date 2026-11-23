// Cloudflare Worker to fetch YouTube captions via the Innertube API and return the timedtext XML. 

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const videoId = url.searchParams.get("v");
    const lang = url.searchParams.get("lang") || "en";

    if (!videoId) {
      return new Response(JSON.stringify({ error: "Missing v param" }), { status: 400 });
    }

    // 1. Fetch player metadata via YouTube Innertube Android client
    const playerRes = await fetch("https://www.youtube.com/youtubei/v1/player?prettyPrint=false", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "User-Agent": "com.google.android.youtube/19.09.37 (Linux; U; Android 11) gzip",
      },
      body: JSON.stringify({
        context: {
          client: { clientName: "ANDROID", clientVersion: "19.09.37", hl: "en", gl: "US" },
        },
        videoId,
      }),
    });

    const playerJson = await playerRes.json();
    const tracks = playerJson?.captions?.playerCaptionsTracklistRenderer?.captionTracks || [];
    if (!tracks.length) {
      return new Response(JSON.stringify({ error: "No captionTracks", tracks: [] }), { status: 404 });
    }

    const chosen =
      tracks.find((t) => t.languageCode === lang) ||
      tracks.find((t) => (t.languageCode || "").startsWith("en")) ||
      tracks[0];

    // 2. Fetch the timedtext XML directly from baseUrl
    const xmlRes = await fetch(chosen.baseUrl);
    const xmlText = await xmlRes.text();

    return new Response(xmlText, {
      status: 200,
      headers: {
        "Content-Type": "application/xml; charset=utf-8",
        "Access-Control-Allow-Origin": "*",
      },
    });
  },
};