import React, { useState, useEffect } from "react";
import Layout from "../components/Layout";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import api from "../services/api";
import { 
  AlertCircle, 
  Home, 
  FileText, 
  Send,
  Wifi,
  Wrench,
  Droplets,
  Sparkles,
  Zap,
  User,
  Building2,
  Loader,
  ShieldAlert,
  X
} from "lucide-react";

const CreateComplaint = () => {
  const [form, setForm] = useState({
    title: "",
    category: "",
    priority: "",
    description: "",
  });

  const [userRoom, setUserRoom] = useState("");
  const [userName, setUserName] = useState("");
  const [loading, setLoading] = useState(false);
  const [fetchingUser, setFetchingUser] = useState(true);
  const { user } = useAuth();
  const navigate = useNavigate();

  // ✨ AI: auto-classify (category + priority + urgency)
  const [aiAnalyzing, setAiAnalyzing] = useState(false);
  const [aiSuggestion, setAiSuggestion] = useState(null); // { category, priority, isUrgent, reason }
  const [aiError, setAiError] = useState("");

  // ✨ AI: duplicate detection modal
  const [checkingDuplicates, setCheckingDuplicates] = useState(false);
  const [duplicates, setDuplicates] = useState([]);
  const [showDuplicateModal, setShowDuplicateModal] = useState(false);

  // Fetch user profile to get room number
  useEffect(() => {
    const fetchUserProfile = async () => {
      try {
        const response = await api.get("/api/auth/profile");
        setUserRoom(response.data.roomNumber || "Not assigned");
        setUserName(response.data.name || user?.name);
      } catch (error) {
        console.error("Error fetching user profile:", error);
        setUserRoom("Not assigned");
      } finally {
        setFetchingUser(false);
      }
    };

    if (user) {
      fetchUserProfile();
    }
  }, [user]);

  const handleChange = (e) => {
    setForm({
      ...form,
      [e.target.name]: e.target.value,
    });
  };

  // ✨ AI: ask the backend to suggest category + priority + urgency from the description
  const handleAiAnalyze = async () => {
    if (!form.description || form.description.trim().length < 10) {
      setAiError("Write a bit more detail first (at least 10 characters).");
      return;
    }
    setAiError("");
    setAiAnalyzing(true);
    setAiSuggestion(null);

    try {
      const res = await api.post("/api/ai/analyze-complaint", {
        description: form.description,
      });

      setAiSuggestion(res.data);
      setForm((f) => ({
        ...f,
        category: res.data.category,
        priority: res.data.isUrgent ? "urgent" : res.data.priority,
      }));
    } catch (error) {
      setAiError(
        error.response?.data?.message ||
          "AI analysis is unavailable right now. Please select category & priority manually."
      );
    } finally {
      setAiAnalyzing(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setAiError("");

    // ✨ AI: check for similar/duplicate open complaints before submitting
    let dupes = [];
    try {
      setCheckingDuplicates(true);
      const dupRes = await api.post("/api/ai/check-duplicates", {
        description: form.description,
        category: form.category,
      });
      dupes = dupRes.data?.duplicates || [];
    } catch (error) {
      // Fail soft: if duplicate check is unavailable, just proceed to submit
      console.warn("Duplicate check unavailable:", error.message);
    } finally {
      setCheckingDuplicates(false);
    }

    if (dupes.length > 0) {
      setDuplicates(dupes);
      setShowDuplicateModal(true);
      setLoading(false);
      return; // wait for the student to confirm or cancel
    }

    await submitComplaint([]);
  };

  // Actually creates the complaint. `duplicateOf` is a list of complaint
  // IDs the student was warned about and chose to submit anyway.
  const submitComplaint = async (duplicateOf) => {
    setLoading(true);
    try {
      // ✅ No need to send roomNumber - backend will get it from user profile
      await api.post("/api/complaints", {
        category: form.category,
        description: form.description,
        priority: form.priority,
        title: form.title,
        duplicateOf,
      });

      alert("Complaint submitted ✅");

      // Reset form
      setForm({
        title: "",
        category: "",
        priority: "",
        description: "",
      });
      setAiSuggestion(null);

      // Redirect to my complaints
      navigate("/my-complaints");

    } catch (error) {
      alert(error.response?.data?.message || "Error submitting complaint");
    } finally {
      setLoading(false);
      setShowDuplicateModal(false);
    }
  };

  // Get icon for category
  const getCategoryIcon = (category) => {
    switch(category) {
      case 'Electrical':
        return <Zap className="h-4 w-4" />;
      case 'Plumbing':
        return <Droplets className="h-4 w-4" />;
      case 'WiFi':
        return <Wifi className="h-4 w-4" />;
      case 'Cleaning':
        return <Sparkles className="h-4 w-4" />;
      default:
        return <Wrench className="h-4 w-4" />;
    }
  };

  if (fetchingUser) {
    return (
      <Layout>
        <div className="flex items-center justify-center min-h-[60vh]">
          <div className="text-center">
            <Loader className="h-8 w-8 text-blue-600 animate-spin mx-auto mb-3" />
            <p className="text-gray-500">Loading your information...</p>
          </div>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="flex justify-center items-center min-h-[80vh] py-8">
        {/* Main Card */}
        <div className="w-full max-w-2xl">
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
            {/* Decorative top bar */}
            <div className="h-1.5 bg-gradient-to-r from-blue-600 to-indigo-600"></div>
            
            <div className="p-8">
              {/* Header */}
              <div className="mb-8">
                <div className="flex items-center gap-3 mb-2">
                  <div className="p-2 bg-blue-50 rounded-lg">
                    <AlertCircle className="h-5 w-5 text-blue-600" />
                  </div>
                  <h2 className="text-2xl font-bold text-gray-800">
                    Create Complaint
                  </h2>
                </div>
                <p className="text-gray-500 text-sm ml-11">
                  Report your issue quickly and clearly. Our team will address it promptly.
                </p>
              </div>

              {/* User Info Banner - Shows room number from profile */}
              <div className="mb-6 p-4 bg-gradient-to-r from-blue-50 to-indigo-50 rounded-xl border border-blue-100">
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-white rounded-lg shadow-sm">
                    <User className="h-5 w-5 text-blue-600" />
                  </div>
                  <div className="flex-1">
                    <p className="text-sm text-gray-600">Submitting complaint as</p>
                    <div className="flex items-center gap-3 mt-1 flex-wrap">
                      <span className="font-semibold text-gray-800">{userName}</span>
                      <span className="text-gray-400">•</span>
                      <div className="flex items-center gap-1">
                        <Building2 className="h-3.5 w-3.5 text-gray-500" />
                        <span className="text-sm text-gray-700">
                          <span className="font-medium">Room {userRoom}</span>
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Form */}
              <form onSubmit={handleSubmit} className="space-y-6">
                {/* Title */}
                <div>
                  <label className="block text-gray-700 text-sm font-semibold mb-2">
                    Title <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    name="title"
                    value={form.title}
                    onChange={handleChange}
                    placeholder="e.g., Water leakage in bathroom"
                    className="w-full px-4 py-2.5 border border-gray-200 rounded-xl text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all duration-200"
                    required
                  />
                </div>

                {/* Row for Category and Priority */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                  {/* Category */}
                  <div>
                    <label className="block text-gray-700 text-sm font-semibold mb-2">
                      Category <span className="text-red-500">*</span>
                    </label>
                    <div className="relative">
                      <select
                        name="category"
                        value={form.category}
                        onChange={handleChange}
                        className="w-full px-4 py-2.5 border border-gray-200 rounded-xl text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all duration-200 appearance-none bg-white cursor-pointer"
                        required
                      >
                        <option value="">Select category</option>
                        <option value="Electrical">⚡ Electrical</option>
                        <option value="Plumbing">💧 Plumbing</option>
                        <option value="WiFi">📡 WiFi</option>
                        <option value="Cleaning">✨ Cleaning</option>
                        <option value="Other">🔧 Other</option>
                      </select>
                      <div className="absolute right-3 top-1/2 transform -translate-y-1/2 pointer-events-none">
                        {form.category && getCategoryIcon(form.category)}
                      </div>
                    </div>
                  </div>

                  {/* Priority */}
                  <div>
                    <label className="block text-gray-700 text-sm font-semibold mb-2">
                      Priority <span className="text-red-500">*</span>
                    </label>
                    <select
                      name="priority"
                      value={form.priority}
                      onChange={handleChange}
                      className="w-full px-4 py-2.5 border border-gray-200 rounded-xl text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all duration-200 bg-white cursor-pointer"
                      required
                    >
                      <option value="">Select priority</option>
                      <option value="low">🟢 Low</option>
                      <option value="medium">🟡 Medium</option>
                      <option value="high">🟠 High</option>
                      <option value="urgent">🔴 Urgent</option>
                    </select>
                  </div>
                </div>

                {/* Description */}
                <div>
                  <label className="block text-gray-700 text-sm font-semibold mb-2">
                    Description <span className="text-red-500">*</span>
                  </label>
                  <div className="relative">
                    <FileText className="absolute left-3 top-3 h-4 w-4 text-gray-400" />
                    <textarea
                      name="description"
                      rows="5"
                      value={form.description}
                      onChange={handleChange}
                      placeholder="Please provide detailed information about the issue..."
                      className="w-full pl-10 pr-4 py-2.5 border border-gray-200 rounded-xl text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all duration-200 resize-none"
                      required
                    />
                  </div>
                  <p className="text-gray-400 text-xs mt-1 ml-1">
                    Be as specific as possible to help us resolve your issue faster
                  </p>

                  {/* ✨ AI Auto-classify button */}
                  <button
                    type="button"
                    onClick={handleAiAnalyze}
                    disabled={aiAnalyzing}
                    className="mt-3 inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-indigo-600 bg-indigo-50 hover:bg-indigo-100 rounded-lg transition-colors disabled:opacity-50"
                  >
                    {aiAnalyzing ? (
                      <>
                        <Loader className="h-3.5 w-3.5 animate-spin" />
                        Analyzing...
                      </>
                    ) : (
                      <>
                        <Sparkles className="h-3.5 w-3.5" />
                        Auto-fill Category & Priority with AI
                      </>
                    )}
                  </button>

                  {aiError && (
                    <p className="text-xs text-red-500 mt-1.5">{aiError}</p>
                  )}

                  {aiSuggestion && (
                    <div
                      className={`mt-3 p-3 rounded-lg border text-sm ${
                        aiSuggestion.isUrgent
                          ? "bg-red-50 border-red-200"
                          : "bg-indigo-50 border-indigo-100"
                      }`}
                    >
                      <div className="flex items-start gap-2">
                        {aiSuggestion.isUrgent ? (
                          <ShieldAlert className="h-4 w-4 text-red-600 mt-0.5 flex-shrink-0" />
                        ) : (
                          <Sparkles className="h-4 w-4 text-indigo-600 mt-0.5 flex-shrink-0" />
                        )}
                        <div>
                          <p className={`font-medium ${aiSuggestion.isUrgent ? "text-red-700" : "text-indigo-700"}`}>
                            {aiSuggestion.isUrgent
                              ? "⚠️ Flagged as a safety-critical issue - priority escalated automatically"
                              : `AI suggested: ${aiSuggestion.category} · ${aiSuggestion.priority} priority`}
                          </p>
                          {aiSuggestion.reason && (
                            <p className="text-gray-500 text-xs mt-0.5">{aiSuggestion.reason}</p>
                          )}
                        </div>
                      </div>
                    </div>
                  )}
                </div>

                {/* Room Information Note */}
                <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                  <p className="text-xs text-gray-500 flex items-center gap-1">
                    <Home className="h-3 w-3" />
                    Complaint will be registered for <strong className="text-gray-700">Room {userRoom}</strong> 
                    (as per your registered profile)
                  </p>
                </div>

                {/* Submit Button */}
                <button
                  type="submit"
                  disabled={loading || checkingDuplicates || userRoom === "Not assigned"}
                  className="w-full py-3 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white font-semibold rounded-xl transition-all duration-200 transform hover:scale-[1.02] disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100 shadow-sm shadow-blue-200 flex items-center justify-center gap-2"
                >
                  {checkingDuplicates ? (
                    <>
                      <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                      <span>Checking for similar complaints...</span>
                    </>
                  ) : loading ? (
                    <>
                      <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                      <span>Submitting...</span>
                    </>
                  ) : (
                    <>
                      <Send className="h-4 w-4" />
                      <span>Submit Complaint</span>
                    </>
                  )}
                </button>

                {/* Footer note */}
                <p className="text-center text-gray-400 text-xs pt-4">
                  Our team will review your complaint and take action within 24-48 hours
                </p>
              </form>
            </div>
          </div>
        </div>
      </div>

      {/* ✨ AI Duplicate Detection Modal */}
      {showDuplicateModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-xl">
            <div className="flex items-start justify-between mb-2">
              <h3 className="text-lg font-bold text-gray-800 flex items-center gap-2">
                ⚠️ Similar complaints found
              </h3>
              <button
                onClick={() => setShowDuplicateModal(false)}
                className="text-gray-400 hover:text-gray-600"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <p className="text-sm text-gray-500 mb-4">
              Our AI found {duplicates.length} open complaint{duplicates.length > 1 ? "s" : ""} that may
              already describe this issue. You can still submit if it's genuinely different.
            </p>
            <div className="space-y-3 max-h-60 overflow-y-auto mb-5">
              {duplicates.map((d) => (
                <div key={d.id} className="p-3 bg-gray-50 rounded-lg border border-gray-100 text-sm">
                  <p className="text-gray-700">{d.description}</p>
                  <p className="text-xs text-gray-400 mt-1.5 flex items-center gap-2 flex-wrap">
                    <span>Room {d.roomNumber}</span>
                    <span>•</span>
                    <span className="capitalize">{d.status}</span>
                    <span>•</span>
                    <span>{d.confidence}% match</span>
                  </p>
                </div>
              ))}
            </div>
            <div className="flex gap-3">
              <button
                onClick={() => setShowDuplicateModal(false)}
                className="flex-1 py-2.5 border border-gray-200 rounded-xl text-gray-600 hover:bg-gray-50 transition-colors font-medium"
              >
                Cancel
              </button>
              <button
                onClick={() => submitComplaint(duplicates.map((d) => d.id))}
                className="flex-1 py-2.5 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition-colors font-medium"
              >
                Submit Anyway
              </button>
            </div>
          </div>
        </div>
      )}
    </Layout>
  );
};

export default CreateComplaint;