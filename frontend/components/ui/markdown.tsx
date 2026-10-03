"use client";

import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";

/**
 * Themed markdown renderer for AI-generated text (incident summaries, etc.).
 * Uses react-markdown + remark-gfm (lists, tables, strikethrough, autolinks).
 * Raw HTML is NOT rendered (react-markdown default), so model output is safe to
 * display. Element styling is mapped to the slate palette here rather than
 * pulling in the typography plugin.
 */
const components: Components = {
  h1: ({ node, ...p }) => (
    <h1 className="mb-1.5 mt-3 text-base font-semibold text-foreground first:mt-0" {...p} />
  ),
  h2: ({ node, ...p }) => (
    <h2 className="mb-1.5 mt-3 text-sm font-semibold text-foreground first:mt-0" {...p} />
  ),
  h3: ({ node, ...p }) => (
    <h3 className="mb-1 mt-2.5 text-sm font-semibold text-foreground first:mt-0" {...p} />
  ),
  p: ({ node, ...p }) => <p className="my-1.5 first:mt-0 last:mb-0" {...p} />,
  a: ({ node, ...p }) => (
    <a
      className="font-medium text-primary underline underline-offset-2 hover:opacity-80"
      target="_blank"
      rel="noreferrer noopener"
      {...p}
    />
  ),
  strong: ({ node, ...p }) => <strong className="font-semibold text-foreground" {...p} />,
  em: ({ node, ...p }) => <em className="italic" {...p} />,
  ul: ({ node, ...p }) => <ul className="my-1.5 list-disc space-y-1 pl-5" {...p} />,
  ol: ({ node, ...p }) => <ol className="my-1.5 list-decimal space-y-1 pl-5" {...p} />,
  li: ({ node, ...p }) => <li className="marker:text-muted-foreground" {...p} />,
  blockquote: ({ node, ...p }) => (
    <blockquote
      className="my-2 border-l-2 border-primary/40 bg-muted/40 py-1 pl-3 text-muted-foreground"
      {...p}
    />
  ),
  hr: () => <hr className="my-3 border-border" />,
  code: ({ node, className, children, ...p }) => {
    const isBlock = /language-/.test(className || "");
    if (isBlock) {
      return (
        <code className={cn("font-mono text-[12.5px]", className)} {...p}>
          {children}
        </code>
      );
    }
    return (
      <code
        className="rounded bg-muted px-1 py-0.5 font-mono text-[12.5px] text-foreground"
        {...p}
      >
        {children}
      </code>
    );
  },
  pre: ({ node, ...p }) => (
    <pre
      className="my-2 overflow-x-auto rounded-md border bg-muted/60 p-3 text-foreground"
      {...p}
    />
  ),
  table: ({ node, ...p }) => (
    <div className="my-2 overflow-x-auto">
      <table className="w-full border-collapse text-xs" {...p} />
    </div>
  ),
  th: ({ node, ...p }) => (
    <th className="border border-border bg-muted/50 px-2 py-1 text-left font-medium" {...p} />
  ),
  td: ({ node, ...p }) => <td className="border border-border px-2 py-1" {...p} />,
};

export function Markdown({
  children,
  className,
}: {
  children: string;
  className?: string;
}) {
  return (
    <div className={cn("text-sm leading-relaxed text-muted-foreground", className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
