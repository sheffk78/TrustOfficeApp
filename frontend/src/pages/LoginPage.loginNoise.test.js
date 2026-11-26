import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom'
import LoginPage from '@/pages/LoginPage'
import { useAuth } from '@/context/AuthContext'
import { toast } from 'sonner'
import { reportErrorToBackend } from '@/utils/errors'

jest.mock('@/context/AuthContext', () => ({ useAuth: jest.fn() }))
jest.mock('sonner', () => ({ toast: { success: jest.fn(), error: jest.fn(), info: jest.fn() } }))
jest.mock('@/utils/errors', () => ({ showError: jest.fn(), reportErrorToBackend: jest.fn() }))
jest.mock('react-router-dom', () => ({
  useSearchParams: () => [new URLSearchParams(''), jest.fn()],
  useNavigate: () => jest.fn(),
  Link: ({ to, children, ...rest }) => <a href={to} {...rest}>{children}</a>,
  useParams: () => ({}),
  useLocation: () => ({ pathname: '/login', search: '' }),
}))

describe('LoginPage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    useAuth.mockReturnValue({
      user: null,
      setUser: jest.fn(),
      loadTrusts: jest.fn(() => Promise.resolve()),
      loadSubscriptionState: jest.fn(() => Promise.resolve()),
    })
  })

  test('passwordless login hint is NOT reported', async () => {
    const STATUS = 401
    const DETAIL = "Your account is ready but no password is set yet. Use 'Forgot password' below to set one — the link is in your welcome email."

    class FakeXHR {
      open() {}
      setRequestHeader() {}
      send() {
        this.readyState = 4
        this.status = STATUS
        this.responseText = JSON.stringify({ detail: DETAIL })
        if (this.onreadystatechange) this.onreadystatechange()
      }
    }

    global.XMLHttpRequest = FakeXHR

    render(<LoginPage />)

    const emailInput = screen.getByTestId('email-input')
    const passwordInput = screen.getByTestId('password-input')
    const form = emailInput.closest('form')

    fireEvent.input(emailInput, { target: { value: 'user@example.com' } })
    fireEvent.input(passwordInput, { target: { value: 'password123' } })
    fireEvent.submit(form)

    await waitFor(() => {
      expect(screen.getByTestId('login-error')).toHaveTextContent('no password is set yet')
    })

    await waitFor(() => {
      expect(reportErrorToBackend).not.toHaveBeenCalled()
    })

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining('no password is set yet')
      )
    })
  })

  test('unexpected error IS reported', async () => {
    const STATUS = 500
    const DETAIL = 'Google OAuth consent failed'

    class FakeXHR {
      open() {}
      setRequestHeader() {}
      send() {
        this.readyState = 4
        this.status = STATUS
        this.responseText = JSON.stringify({ detail: DETAIL })
        if (this.onreadystatechange) this.onreadystatechange()
      }
    }

    global.XMLHttpRequest = FakeXHR

    render(<LoginPage />)

    const emailInput = screen.getByTestId('email-input')
    const passwordInput = screen.getByTestId('password-input')
    const form = emailInput.closest('form')

    fireEvent.input(emailInput, { target: { value: 'user@example.com' } })
    fireEvent.input(passwordInput, { target: { value: 'password123' } })
    fireEvent.submit(form)

    await waitFor(() => {
      expect(reportErrorToBackend).toHaveBeenCalled()
    })
  })
})
