import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** End an anonymous browser session without touching its retained bad-case Trace. */
export async function POST(): Promise<Response> {
  const response = new NextResponse(null, { status: 204 });
  response.cookies.set("gerclaw_guest_token", "", {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 0,
  });
  return response;
}
