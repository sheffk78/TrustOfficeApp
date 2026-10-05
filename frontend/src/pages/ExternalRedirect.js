import { useEffect } from 'react';

/**
 * Legacy booking-link healing (2026-10-05, Jeff-approved).
 *
 * Lead emails sent before 2026-10-05 pointed booking CTAs at this app's
 * domain, where those routes never existed (404). The real, working
 * scheduler lives on the marketing site; the course lives there too.
 *
 * This component sends anyone landing on:
 *   /book          -> https://trustoffice.app/book-a-call/
 *   /book-a-call   -> https://trustoffice.app/book-a-call/
 *   /meeting       -> https://trustoffice.app/book-a-call/
 *   /trustee-101   -> https://trustoffice.app/trustee-101/
 * so every broken link already sitting in a prospect's inbox heals itself.
 *
 * NOTE: plain window.location.replace in an effect — <Navigate> only accepts
 * INTERNAL paths (it would crash on an absolute external URL).
 */
export default function ExternalRedirect(props) {
  const { to } = props;
  useEffect(() => {
    window.location.replace(to);
  }, [to]);
  return null;
}