import React, { createContext, useState, useContext, useEffect } from 'react';
import axios from 'axios';
import { authAPI } from '../lib/api';

const AuthContext = createContext(null);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  // Initialize auth state on component mount
  useEffect(() => {
    // Check if user is already authenticated by making a request
    // If the cookie exists, the request will succeed
    const checkAuth = async () => {
      try {
        // Try to access a protected route to verify authentication
        // Note: This endpoint should be added to your backend
        // For now, we'll assume the user is authenticated if we have a cookie
        const token = document.cookie.includes('access_token');
        if (token) {
          setIsAuthenticated(true);
        }
      } catch (error) {
        setIsAuthenticated(false);
        setUser(null);
      } finally {
        setLoading(false);
      }
    };
    
    checkAuth();
  }, []);

  /**
   * Login user with email and password.
   * JWT token is stored in HTTP-only cookie by backend.
   */
  const login = async (email, password) => {
    try {
      const response = await authAPI.login(email, password);
      const { access_token } = response.data;
      
      // Token is automatically stored in HTTP-only cookie by the backend
      // We only track authentication state in React
      setUser({ email });
      setIsAuthenticated(true);
      
      return response.data;
    } catch (error) {
      setIsAuthenticated(false);
      setUser(null);
      throw error;
    }
  };

  /**
   * Register new user.
   * JWT token is stored in HTTP-only cookie by backend.
   */
  const register = async (email, password, full_name) => {
    try {
      const response = await authAPI.register(email, password, full_name);
      const { access_token } = response.data;
      
      // Token is automatically stored in HTTP-only cookie by the backend
      // We only track authentication state in React
      setUser({ email, full_name });
      setIsAuthenticated(true);
      
      return response.data;
    } catch (error) {
      setIsAuthenticated(false);
      setUser(null);
      throw error;
    }
  };

  /**
   * Logout user and clear authentication.
   * Backend will clear the HTTP-only cookie.
   */
  const logout = async () => {
    try {
      await authAPI.logout();
    } catch (error) {
      console.error('Logout error:', error);
    } finally {
      // Clear local state regardless of backend response
      setUser(null);
      setIsAuthenticated(false);
    }
  };

  return (
    <AuthContext.Provider 
      value={{ 
        user, 
        loading, 
        isAuthenticated,
        token: isAuthenticated, // For backward compatibility
        login, 
        register, 
        logout 
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};
