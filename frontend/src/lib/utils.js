import { clsx } from "clsx";
import { twMerge } from "tailwind-merge"

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}

/**
 * Extract error message from API error response.
 * Handles both string errors and Pydantic validation error arrays.
 * 
 * @param {Object} error - Axios error object
 * @param {string} fallback - Fallback message if no error details found
 * @returns {string} - Formatted error message
 */
export const getErrorMessage = (error, fallback = 'An error occurred') => {
  if (!error?.response?.data?.detail) {
    return fallback;
  }

  const detail = error.response.data.detail;

  // If detail is a string, return it directly
  if (typeof detail === 'string') {
    return detail;
  }

  // If detail is an array (Pydantic validation errors)
  if (Array.isArray(detail)) {
    // Extract all error messages
    const messages = detail.map(err => {
      if (err.msg) {
        // Include field location if available
        const field = err.loc && err.loc.length > 1 ? err.loc[err.loc.length - 1] : null;
        return field ? `${field}: ${err.msg}` : err.msg;
      }
      return 'Validation error';
    });

    // Join multiple messages with line breaks, or return first message
    return messages.length > 1 ? messages.join('; ') : messages[0] || fallback;
  }

  // If detail is an object, try to extract message
  if (typeof detail === 'object' && detail.msg) {
    return detail.msg;
  }

  return fallback;
};
