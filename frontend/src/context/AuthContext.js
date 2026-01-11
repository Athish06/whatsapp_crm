import React, { createContext, useState, useContext, useEffect } from 'react';
import axios from 'axios';

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
  const [token, setToken] = useState(localStorage.getItem('token'));
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const storedToken = localStorage.getItem('token');
    if (storedToken) {
      setToken(storedToken);
      axios.defaults.headers.common['Authorization'] = `Bearer ${storedToken}`;
    }
    setLoading(false);
  }, []);

  const login = async (email, password) => {
    const response = await axios.post(
      `${process.env.REACT_APP_BACKEND_URL}/api/auth/login`,
      { email, password }
    );
    const { access_token } = response.data;
    localStorage.setItem('token', access_token);
    setToken(access_token);
    axios.defaults.headers.common['Authorization'] = `Bearer ${access_token}`;
    setUser({ email });
    return response.data;
  };

  const register = async (email, password, full_name) => {
    const response = await axios.post(
      `${process.env.REACT_APP_BACKEND_URL}/api/auth/register`,
      { email, password, full_name }
    );
    const { access_token } = response.data;
    localStorage.setItem('token', access_token);
    setToken(access_token);
    axios.defaults.headers.common['Authorization'] = `Bearer ${access_token}`;
    setUser({ email, full_name });
    return response.data;
  };

  const logout = () => {
    localStorage.removeItem('token');
    setToken(null);
    setUser(null);
    delete axios.defaults.headers.common['Authorization'];
  };

  return (
    <AuthContext.Provider value={{ user, token, login, register, logout, loading }}>
      {children}
    </AuthContext.Provider>
  );
};
