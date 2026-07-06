// Stub: replace with real Supabase client when Supabase auth is integrated.
// engineClient.ts depends on supabase.auth.getSession() to forward the JWT.

interface Session {
  access_token: string;
}

interface SessionResponse {
  data: { session: Session | null };
  error: { message: string } | null;
}

interface Auth {
  getSession(): Promise<SessionResponse>;
}

interface SupabaseClient {
  auth: Auth;
}

const stub: SupabaseClient = {
  auth: {
    async getSession() {
      return {
        data: { session: null },
        error: { message: "Supabase not configured — stub client" },
      };
    },
  },
};

export const supabase = stub;
