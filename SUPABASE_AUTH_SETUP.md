# Supabase Auth Setup Guide

I've updated the code to use Supabase Auth for email verification. Follow these steps to complete the setup:

## Step 1: Update Users Table

Run this SQL in your Supabase SQL Editor to update the users table:

```sql
-- Drop the old users table (backup data if needed first!)
DROP TABLE IF EXISTS users;

-- Create new users table that works with Supabase Auth
CREATE TABLE users (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    is_verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Disable RLS (as per your preference)
ALTER TABLE users DISABLE ROW LEVEL SECURITY;

-- Update blogs table to reference Supabase Auth users
-- First, if there are existing blogs, we need to handle them
-- For now, let's just update the foreign key constraint

-- Remove old foreign key if exists (might fail if it doesn't exist, that's OK)
ALTER TABLE blogs DROP CONSTRAINT IF EXISTS blogs_user_id_fkey;

-- The user_id in blogs will now be a UUID from Supabase Auth
-- Existing blogs with old user_ids will need to be handled manually
```

## Step 2: Configure Supabase Auth Settings

Go to your Supabase Dashboard → Authentication → Configuration:

### Email Templates
1. Go to **Email Templates** section
2. Customize the confirmation email template if desired
3. Make sure "Enable email confirmations" is turned ON

### URL Configuration
1. Go to **URL Configuration** section
2. Set **Site URL**: `http://127.0.0.1:5000` (for local development)
3. Add **Redirect URLs**:
   - `http://127.0.0.1:5000/auth/callback`
   - `http://127.0.0.1:5000/login`
   - `http://localhost:5000/auth/callback`
   - `http://localhost:5000/login`

### Email Provider (IMPORTANT!)
1. Go to **Email** section under Auth
2. **For testing**: Supabase has a built-in email provider that works for development
3. **For production**: You'll need to set up a custom SMTP provider:
   - Resend (free tier available)
   - SendGrid
   - Mailgun
   - Your own SMTP server

### Rate Limits
1. The free tier allows 4 emails per hour
2. For production, consider upgrading or using a custom SMTP

## Step 3: Test the Authentication Flow

1. Start your Flask app: `python app.py`
2. Go to `/signup` and create an account
3. Check your email for the verification link
4. Click the verification link
5. Login with your credentials

## How It Works Now

### Signup Flow:
1. User fills out signup form (name, email, password)
2. Supabase Auth creates the user and sends verification email automatically
3. User data is also saved to our `users` table for name storage
4. User is redirected to login page

### Verification Flow:
1. User clicks link in email
2. Supabase handles verification automatically
3. User can now login with full access

### Login Flow:
1. User enters email and password
2. Supabase Auth verifies credentials
3. We check `email_confirmed_at` to see if verified
4. Session is created with user info

## Troubleshooting

### "Email not confirmed" error
- The user needs to click the verification link in their email
- Check spam folder
- Use "Resend Verification" button

### Emails not sending
- Check Supabase Auth → Logs for errors
- Verify rate limits haven't been exceeded (4/hour on free tier)
- Make sure email confirmations are enabled in settings

### Redirect issues after email verification
- Make sure redirect URLs are configured in Supabase dashboard
- The callback URL must match exactly

## Production Considerations

For production deployment:
1. Update Site URL to your production domain
2. Add production redirect URLs
3. Set up a custom SMTP provider for reliable email delivery
4. Consider enabling additional auth methods (Google, GitHub, etc.)
