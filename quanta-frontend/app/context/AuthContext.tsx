"use client";

import { createContext, useContext, useEffect, useState } from "react";

interface User {
  user_id: string;
  email: string;
  name: string;
  picture_url: string;
}

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  refreshAuth: () => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

function getApiBaseUrl(): string {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL;
  if (!baseUrl) {
    throw new Error("NEXT_PUBLIC_API_URL n'est pas configurée.");
  }
  return baseUrl.replace(/\/$/, "");
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const refreshAuth = async () => {
    try {
      const baseUrl = getApiBaseUrl();
      const response = await fetch(`${baseUrl}/auth/me`, {
        method: "GET",
        credentials: "include",
      });

      if (response.ok) {
        const userData = await response.json();
        setUser(userData);
      } else if (response.status === 401) {
        // 401 explicite = utilisateur non connecté (déconnexion normale)
        setUser(null);
      }
      // Autres erreurs (500, 502, etc.) = erreur serveur temporaire, on ne déconnecte pas
      // L'utilisateur reste connecté avec l'état précédent
    } catch {
      // Erreur réseau = on ne déconnecte pas, l'utilisateur reste connecté avec l'état précédent
      // Le cookie est peut-être encore valide
    } finally {
      setIsLoading(false);
    }
  };

  const logout = async () => {
    try {
      const baseUrl = getApiBaseUrl();
      await fetch(`${baseUrl}/auth/logout`, {
        method: "POST",
        credentials: "include",
      });
    } catch {
      // Ignorer les erreurs de logout
    } finally {
      setUser(null);
    }
  };

  useEffect(() => {
    void refreshAuth();
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: user !== null,
        refreshAuth,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth doit être utilisé dans un AuthProvider");
  }
  return context;
}
