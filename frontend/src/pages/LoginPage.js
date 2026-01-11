import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Lock, Mail, User } from 'lucide-react';

const LoginPage = () => {
  const [isLogin, setIsLogin] = useState(true);
  const [formData, setFormData] = useState({
    email: '',
    password: '',
    full_name: ''
  });
  const [loading, setLoading] = useState(false);
  const { login, register } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      if (isLogin) {
        await login(formData.email, formData.password);
        toast.success('Login successful');
      } else {
        await register(formData.email, formData.password, formData.full_name);
        toast.success('Registration successful');
      }
      navigate('/dashboard');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Authentication failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex">
      {/* Left side - Form */}
      <div className="w-full lg:w-1/2 flex items-center justify-center p-8 bg-[#121212]">
        <div className="w-full max-w-md">
          <div className="mb-8">
            <h1 className="text-4xl font-bold mb-2" style={{ fontFamily: 'Chivo, sans-serif' }}>
              WhatsApp CRM Pro
            </h1>
            <p className="text-muted-foreground">
              Manage your bulk messaging campaigns efficiently
            </p>
          </div>

          <div className="bg-[#1C1C1C] border border-[#2E2E2E] rounded-lg p-8">
            <div className="mb-6">
              <h2 className="text-2xl font-semibold mb-2">
                {isLogin ? 'Sign In' : 'Create Account'}
              </h2>
              <p className="text-sm text-muted-foreground">
                {isLogin ? 'Welcome back!' : 'Get started with your account'}
              </p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4" data-testid="login-form">
              {!isLogin && (
                <div>
                  <label className="block text-sm font-medium mb-2">
                    Full Name
                  </label>
                  <div className="relative">
                    <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <input
                      data-testid="full-name-input"
                      type="text"
                      value={formData.full_name}
                      onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                      className="w-full bg-[#121212] border border-[#2E2E2E] focus:border-[#3ECF8E] focus:ring-1 focus:ring-[#3ECF8E] rounded-md h-10 pl-10 pr-3 text-sm transition-colors outline-none"
                      placeholder="John Doe"
                      required={!isLogin}
                    />
                  </div>
                </div>
              )}

              <div>
                <label className="block text-sm font-medium mb-2">
                  Email
                </label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <input
                    data-testid="email-input"
                    type="email"
                    value={formData.email}
                    onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                    className="w-full bg-[#121212] border border-[#2E2E2E] focus:border-[#3ECF8E] focus:ring-1 focus:ring-[#3ECF8E] rounded-md h-10 pl-10 pr-3 text-sm transition-colors outline-none"
                    placeholder="you@example.com"
                    required
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">
                  Password
                </label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <input
                    data-testid="password-input"
                    type="password"
                    value={formData.password}
                    onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                    className="w-full bg-[#121212] border border-[#2E2E2E] focus:border-[#3ECF8E] focus:ring-1 focus:ring-[#3ECF8E] rounded-md h-10 pl-10 pr-3 text-sm transition-colors outline-none"
                    placeholder="••••••••"
                    required
                  />
                </div>
              </div>

              <button
                data-testid="submit-button"
                type="submit"
                disabled={loading}
                className="w-full bg-[#3ECF8E] text-black hover:bg-[#34B27B] font-medium rounded-md h-10 shadow-[0_0_10px_rgba(62,207,142,0.2)] transition-all disabled:opacity-50"
              >
                {loading ? 'Please wait...' : (isLogin ? 'Sign In' : 'Create Account')}
              </button>
            </form>

            <div className="mt-6 text-center">
              <button
                data-testid="toggle-mode-button"
                onClick={() => setIsLogin(!isLogin)}
                className="text-sm text-muted-foreground hover:text-white transition-colors"
              >
                {isLogin ? "Don't have an account? Sign up" : 'Already have an account? Sign in'}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Right side - Image */}
      <div 
        className="hidden lg:block lg:w-1/2 bg-cover bg-center relative"
        style={{ backgroundImage: 'url(https://images.unsplash.com/photo-1762278804768-7109128de73f?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NDk1Nzh8MHwxfHNlYXJjaHwxfHxhYnN0cmFjdCUyMGRpZ2l0YWwlMjBuZXR3b3JrJTIwZ3JlZW4lMjBkYXJrJTIwYmFja2dyb3VuZHxlbnwwfHx8fDE3NjgxMzQ0MzB8MA&ixlib=rb-4.1.0&q=85)' }}
      >
        <div className="absolute inset-0 bg-black/80"></div>
        <div className="absolute inset-0 flex items-center justify-center p-12">
          <div className="text-center">
            <h2 className="text-5xl font-bold mb-4" style={{ fontFamily: 'Chivo, sans-serif' }}>
              Reach Thousands<br />In Minutes
            </h2>
            <p className="text-xl text-muted-foreground">
              Powerful bulk messaging with smart customer classification
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default LoginPage;
