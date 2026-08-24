import type { SVGProps } from 'react'

type Props = SVGProps<SVGSVGElement> & { size?: number }

function Icon({ size = 18, children, ...props }: Props) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {children}
    </svg>
  )
}

export const ChatIcon = (props: Props) => <Icon {...props}><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v7a2.5 2.5 0 0 1-2.5 2.5H10l-5 4v-4.6A2.5 2.5 0 0 1 4 12.5z" /></Icon>
export const PrescriptionIcon = (props: Props) => <Icon {...props}><path d="M7 3h10v18H7z" /><path d="M9.5 8h5M9.5 12h5M9.5 16H12" /><path d="M10 3V1.8h4V3" /></Icon>
export const AssessmentIcon = (props: Props) => <Icon {...props}><path d="M5 4h14v17H5z" /><path d="m8 9 1.5 1.5L12 8M8 15h8M14 10h2" /></Icon>
export const MedicationIcon = (props: Props) => <Icon {...props}><path d="M8.2 5.2a4.2 4.2 0 0 1 5.9 0l4.7 4.7a4.2 4.2 0 0 1-5.9 5.9l-4.7-4.7a4.2 4.2 0 0 1 0-5.9Z" /><path d="m10.6 13.5 5.9-5.9" /></Icon>
export const ProfileIcon = (props: Props) => <Icon {...props}><circle cx="12" cy="8" r="3" /><path d="M5.5 20a6.5 6.5 0 0 1 13 0" /><path d="M4 4h2M18 4h2" /></Icon>
export const MoreIcon = (props: Props) => <Icon {...props}><circle cx="5" cy="12" r="1" fill="currentColor" /><circle cx="12" cy="12" r="1" fill="currentColor" /><circle cx="19" cy="12" r="1" fill="currentColor" /></Icon>
export const SettingsIcon = (props: Props) => <Icon {...props}><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3A1.7 1.7 0 0 0 10 3V2.8h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z" /></Icon>
export const CloseIcon = (props: Props) => <Icon {...props}><path d="m6 6 12 12M18 6 6 18" /></Icon>
export const UploadIcon = (props: Props) => <Icon {...props}><path d="M12 16V4" /><path d="m7.5 8.5 4.5-4.5 4.5 4.5" /><path d="M5 14v5h14v-5" /></Icon>
