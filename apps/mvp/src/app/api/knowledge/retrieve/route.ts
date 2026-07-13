import { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(_request: NextRequest): Promise<Response> {
  void _request;
  return Response.json(
    { success: false, error: "本地知识库功能正在维护中", chunks: [], total: 0 },
    { status: 503 }
  );
}
