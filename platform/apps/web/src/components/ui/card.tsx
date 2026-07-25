import { type HTMLAttributes, type ReactNode } from 'react';
import clsx from 'clsx';

/* ── Card ───────────────────────────────────────────── */
interface CardProps extends HTMLAttributes<HTMLDivElement> {
  hover?: boolean;
}

export function Card({ hover = false, className, children, ...props }: CardProps) {
  return (
    <div
      className={clsx(
        'rounded-xl border border-border bg-surface shadow-sm transition-all duration-300',
        hover && 'hover:shadow-glow hover:-translate-y-0.5 hover:border-primary/30 cursor-pointer',
        className
      )}
      {...props}
    >
      {children}
    </div>
  );
}

/* ── CardHeader ─────────────────────────────────────── */
interface CardHeaderProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
}

export function CardHeader({ className, children, ...props }: CardHeaderProps) {
  return (
    <div className={clsx('flex flex-col gap-1.5 p-6 pb-3', className)} {...props}>
      {children}
    </div>
  );
}

/* ── CardTitle ──────────────────────────────────────── */
interface CardTitleProps extends HTMLAttributes<HTMLHeadingElement> {
  children: ReactNode;
}

export function CardTitle({ className, children, ...props }: CardTitleProps) {
  return (
    <h3 className={clsx('text-lg font-semibold text-text', className)} {...props}>
      {children}
    </h3>
  );
}

/* ── CardDescription ────────────────────────────────── */
interface CardDescriptionProps extends HTMLAttributes<HTMLParagraphElement> {
  children: ReactNode;
}

export function CardDescription({ className, children, ...props }: CardDescriptionProps) {
  return (
    <p className={clsx('text-sm text-text-muted', className)} {...props}>
      {children}
    </p>
  );
}

/* ── CardContent ────────────────────────────────────── */
interface CardContentProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
}

export function CardContent({ className, children, ...props }: CardContentProps) {
  return (
    <div className={clsx('p-6 pt-3', className)} {...props}>
      {children}
    </div>
  );
}

/* ── CardFooter ─────────────────────────────────────── */
interface CardFooterProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
}

export function CardFooter({ className, children, ...props }: CardFooterProps) {
  return (
    <div
      className={clsx(
        'flex items-center gap-3 border-t border-border px-6 py-4',
        className
      )}
      {...props}
    >
      {children}
    </div>
  );
}
