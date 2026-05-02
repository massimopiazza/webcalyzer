import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { BookOpen, ChevronDown, ChevronRight, Cpu, Menu, X } from "lucide-react";
import { renderToString } from "katex";
import "katex/dist/katex.min.css";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { DOC_GROUPS, type DocsGroup, type DocsPage } from "@/lib/docsNav";
import { cn } from "@/lib/utils";

type Heading = {
  level: 2 | 3;
  text: string;
  id: string;
};

type TocNode = {
  heading: Heading;
  children: Heading[];
};

const MERMAID_CONFIG = {
  startOnLoad: false,
  securityLevel: "strict",
  theme: "base",
  themeVariables: {
    background: "transparent",
    primaryColor: "#101827",
    primaryTextColor: "#e7eef8",
    primaryBorderColor: "#38c7f4",
    secondaryColor: "#151c2d",
    secondaryTextColor: "#d8e2ee",
    secondaryBorderColor: "#314159",
    tertiaryColor: "#0b1020",
    tertiaryTextColor: "#d8e2ee",
    tertiaryBorderColor: "#263247",
    lineColor: "#7a8797",
    textColor: "#e7eef8",
    mainBkg: "#101827",
    nodeBorder: "#38c7f4",
    clusterBkg: "#0f1626",
    clusterBorder: "#2a3851",
    edgeLabelBackground: "#0b1020",
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
  },
  flowchart: {
    curve: "basis",
    htmlLabels: true,
    padding: 12,
  },
} as const;

function slugify(text: string): string {
  return text
    .replace(/<[^>]*>/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function extractHeadings(markdown: string): Heading[] {
  const headings: Heading[] = [];
  for (const line of markdown.split("\n")) {
    const h2 = line.match(/^##\s+(.+)$/);
    const h3 = line.match(/^###\s+(.+)$/);
    if (h2) headings.push({ level: 2, text: h2[1].trim(), id: slugify(h2[1]) });
    if (h3) headings.push({ level: 3, text: h3[1].trim(), id: slugify(h3[1]) });
  }
  return headings;
}

function buildTocTree(headings: Heading[]): TocNode[] {
  const tree: TocNode[] = [];
  let current: TocNode | null = null;
  for (const heading of headings) {
    if (heading.level === 2) {
      current = { heading, children: [] };
      tree.push(current);
    } else if (current) {
      current.children.push(heading);
    }
  }
  return tree;
}

function renderLatex(source: string, displayMode: boolean): string {
  try {
    return renderToString(source, {
      displayMode,
      throwOnError: false,
      strict: false,
      trust: false,
      output: "html",
    });
  } catch {
    return `<code>${escapeHtml(source)}</code>`;
  }
}

function renderInline(source: string): string {
  return source
    .split(/(`[^`]*`)/g)
    .map((segment) => {
      if (segment.startsWith("`") && segment.endsWith("`")) {
        return `<code>${escapeHtml(segment.slice(1, -1))}</code>`;
      }
      const math: string[] = [];
      const withMathTokens = segment.replace(/\$([^$\n]+)\$/g, (_match, expression: string) => {
        const token = `@@MATH_${math.length}@@`;
        math.push(renderLatex(expression, false));
        return token;
      });
      let html = escapeHtml(withMathTokens);
      html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
      html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_match, label: string, href: string) => {
        const safeLabel = label;
        const rawHref = href.trim();
        const mdLink = rawHref.match(/^([A-Za-z0-9._/-]+)\.md(?:#([A-Za-z0-9_-]+))?$/);
        if (mdLink) {
          const rawPath = mdLink[1];
          const page = rawPath.split("/").pop();
          const anchor = mdLink[2];
          const group =
            rawPath.includes("user/") || rawPath.startsWith("user")
              ? "user"
              : rawPath.includes("internal/") || rawPath.startsWith("internal")
                ? "internal"
                : null;
          const groupAttr = group ? ` data-group="${group}"` : "";
          return anchor
            ? `<a href="#${anchor}" data-page="${page}" data-anchor="${anchor}"${groupAttr}>${safeLabel}</a>`
            : `<a href="#" data-page="${page}"${groupAttr}>${safeLabel}</a>`;
        }
        if (rawHref.startsWith("#")) {
          const anchor = rawHref.slice(1);
          return `<a href="#${anchor}" data-anchor="${anchor}">${safeLabel}</a>`;
        }
        if (/^https?:\/\//.test(rawHref)) {
          return `<a href="${escapeHtml(rawHref)}" target="_blank" rel="noreferrer">${safeLabel}</a>`;
        }
        return `<a href="${escapeHtml(rawHref)}">${safeLabel}</a>`;
      });
      math.forEach((rendered, index) => {
        html = html.replace(`@@MATH_${index}@@`, rendered);
      });
      return html;
    })
    .join("");
}

function markerParagraph(rawParagraph: string): string | null {
  const note = rawParagraph.match(/^(Note:)\s*(.*)$/);
  if (note) {
    return `<p class="docs-note"><strong>${note[1]}</strong> ${renderInline(note[2])}</p>`;
  }
  const remark = rawParagraph.match(/^(Remark:)\s*(.*)$/);
  if (remark) {
    return `<p class="docs-remark"><strong>${remark[1]}</strong> ${renderInline(remark[2])}</p>`;
  }
  return null;
}

function isTableSeparator(line: string): boolean {
  return /^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$/.test(line.trim());
}

function parseTableRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function isBlockStart(line: string, nextLine?: string): boolean {
  const trimmed = line.trim();
  return (
    trimmed === "" ||
    /^#{1,4}\s+/.test(trimmed) ||
    trimmed.startsWith("```") ||
    trimmed === "$$" ||
    trimmed.startsWith(">") ||
    /^-\s+/.test(trimmed) ||
    /^\d+\.\s+/.test(trimmed) ||
    (trimmed.startsWith("|") && !!nextLine && isTableSeparator(nextLine))
  );
}

export function renderMarkdown(markdown: string): string {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const html: string[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();
    const next = lines[i + 1];

    if (!trimmed) {
      i += 1;
      continue;
    }

    if (trimmed.startsWith("```")) {
      const language = trimmed.slice(3).trim();
      const code: string[] = [];
      i += 1;
      while (i < lines.length && !lines[i].trim().startsWith("```")) {
        code.push(lines[i]);
        i += 1;
      }
      i += 1;
      if (language === "mermaid") {
        const source = code.join("\n");
        html.push(
          `<div class="docs-mermaid" data-mermaid-source="${escapeHtml(encodeURIComponent(source))}">${escapeHtml(source)}</div>`,
        );
        continue;
      }
      html.push(`<pre><code class="language-${escapeHtml(language)}">${escapeHtml(code.join("\n"))}</code></pre>`);
      continue;
    }

    if (trimmed === "$$") {
      const math: string[] = [];
      i += 1;
      while (i < lines.length && lines[i].trim() !== "$$") {
        math.push(lines[i]);
        i += 1;
      }
      i += 1;
      html.push(`<div class="docs-math-block">${renderLatex(math.join("\n"), true)}</div>`);
      continue;
    }

    const heading = trimmed.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      const level = heading[1].length;
      const text = heading[2].trim();
      const id = slugify(text);
      html.push(`<h${level} id="${id}">${renderInline(text)}</h${level}>`);
      i += 1;
      continue;
    }

    if (trimmed.startsWith("|") && next && isTableSeparator(next)) {
      const header = parseTableRow(trimmed);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        rows.push(parseTableRow(lines[i]));
        i += 1;
      }
      const headHtml = header.map((cell) => `<th>${renderInline(cell)}</th>`).join("");
      const bodyHtml = rows
        .map((row) => `<tr>${row.map((cell) => `<td>${renderInline(cell)}</td>`).join("")}</tr>`)
        .join("");
      html.push(`<div class="docs-table-scroll"><table><thead><tr>${headHtml}</tr></thead><tbody>${bodyHtml}</tbody></table></div>`);
      continue;
    }

    if (trimmed.startsWith(">")) {
      const quote: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith(">")) {
        quote.push(lines[i].trim().replace(/^>\s?/, ""));
        i += 1;
      }
      html.push(`<blockquote>${renderInline(quote.join(" "))}</blockquote>`);
      continue;
    }

    if (/^-\s+/.test(trimmed)) {
      const items: string[] = [];
      while (i < lines.length && /^-\s+/.test(lines[i].trim())) {
        items.push(`<li>${renderInline(lines[i].trim().replace(/^-\s+/, ""))}</li>`);
        i += 1;
      }
      html.push(`<ul>${items.join("")}</ul>`);
      continue;
    }

    if (/^\d+\.\s+/.test(trimmed)) {
      const items: string[] = [];
      while (i < lines.length && /^\d+\.\s+/.test(lines[i].trim())) {
        items.push(`<li>${renderInline(lines[i].trim().replace(/^\d+\.\s+/, ""))}</li>`);
        i += 1;
      }
      html.push(`<ol>${items.join("")}</ol>`);
      continue;
    }

    const paragraph: string[] = [];
    while (i < lines.length && !isBlockStart(lines[i], lines[i + 1])) {
      paragraph.push(lines[i].trim());
      i += 1;
    }
    const rawParagraph = paragraph.join(" ");
    const content = renderInline(rawParagraph);
    html.push(markerParagraph(rawParagraph) ?? `<p>${content}</p>`);
  }

  return html.join("\n");
}

function DocsNav({
  group,
  currentPage,
  activeAnchor,
  expandedPageIds,
  onSelectPage,
  onTogglePage,
  onSelectAnchor,
}: {
  group: DocsGroup;
  currentPage: DocsPage;
  activeAnchor: string | null;
  expandedPageIds: Set<string>;
  onSelectPage: (pageId: string) => void;
  onTogglePage: (pageId: string) => void;
  onSelectAnchor: (pageId: string, anchor: string) => void;
}) {
  return (
    <nav className="min-h-0 flex-1 space-y-1 overflow-y-auto pr-1">
      {group.pages.map((page) => {
        const isActive = page.id === currentPage.id;
        const isExpanded = expandedPageIds.has(page.id);
        const toc = buildTocTree(extractHeadings(page.content));
        const hasToc = toc.length > 0;
        return (
          <div key={page.id}>
            <div
              className={cn(
                "flex w-full items-center rounded-md transition-colors",
                isActive
                  ? "bg-sidebar-accent text-primary"
                  : "text-muted-foreground hover:bg-sidebar-accent/70 hover:text-foreground",
              )}
            >
              {hasToc ? (
                <button
                  type="button"
                  className="flex h-8 w-7 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground"
                  onClick={() => onTogglePage(page.id)}
                  aria-expanded={isExpanded}
                  aria-label={`${isExpanded ? "Collapse" : "Expand"} ${page.title}`}
                >
                  {isExpanded ? (
                    <ChevronDown className="h-3.5 w-3.5" />
                  ) : (
                    <ChevronRight className="h-3.5 w-3.5" />
                  )}
                </button>
              ) : (
                <span className="h-8 w-7 shrink-0" aria-hidden="true" />
              )}
              <button
                type="button"
                className="min-w-0 flex-1 px-1 py-1.5 text-left text-sm transition-colors"
                onClick={() => onSelectPage(page.id)}
              >
                <span className="block truncate">{page.title}</span>
              </button>
            </div>
            {isExpanded && hasToc && (
              <div className="ml-4 mt-1 border-l border-border/70 pl-2">
                {toc.map((node) => (
                  <div key={node.heading.id}>
                    <button
                      className={cn(
                        "block w-full truncate rounded px-2 py-1 text-left text-xs transition-colors",
                        isActive && activeAnchor === node.heading.id
                          ? "text-primary"
                          : "text-muted-foreground hover:text-foreground",
                      )}
                      onClick={() => onSelectAnchor(page.id, node.heading.id)}
                    >
                      {node.heading.text}
                    </button>
                    {node.children.map((child) => (
                      <button
                        key={child.id}
                        className={cn(
                          "ml-3 block w-[calc(100%-0.75rem)] truncate rounded px-2 py-0.5 text-left text-[11px] transition-colors",
                          isActive && activeAnchor === child.id
                            ? "text-primary"
                            : "text-muted-foreground/80 hover:text-foreground",
                        )}
                        onClick={() => onSelectAnchor(page.id, child.id)}
                      >
                        {child.text}
                      </button>
                    ))}
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </nav>
  );
}

export function DocumentationPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [activeAnchor, setActiveAnchor] = useState<string | null>(null);
  const [expandedPagesByGroup, setExpandedPagesByGroup] = useState<Record<string, string[]>>({
    user: ["index"],
    internal: ["index"],
  });
  const contentRef = useRef<HTMLDivElement | null>(null);

  const groupId = searchParams.get("group") === "internal" ? "internal" : "user";
  const currentGroup = DOC_GROUPS.find((group) => group.id === groupId) ?? DOC_GROUPS[0];
  const pageId = searchParams.get("page") ?? "index";
  const currentPage =
    currentGroup.pages.find((page) => page.id === pageId) ?? currentGroup.pages[0];
  const renderedHtml = useMemo(() => renderMarkdown(currentPage.content), [currentPage.content]);
  const expandedPageIds = useMemo(
    () => new Set([...(expandedPagesByGroup[groupId] ?? []), currentPage.id]),
    [currentPage.id, expandedPagesByGroup, groupId],
  );

  useEffect(() => {
    const root = contentRef.current;
    if (!root) return;

    let isCurrent = true;
    const nodes = Array.from(root.querySelectorAll<HTMLElement>(".docs-mermaid"));
    if (nodes.length === 0) return;

    const pageKey = `${groupId}-${currentPage.id}`.replace(/[^a-zA-Z0-9_-]/g, "-");
    const renderKey = `${pageKey}-${Date.now().toString(36)}`;

    const renderDiagrams = async () => {
      const { default: mermaid } = await import("mermaid");
      mermaid.initialize(MERMAID_CONFIG);

      await Promise.all(
        nodes.map(async (node, index) => {
          const encodedSource = node.dataset.mermaidSource ?? "";
          let source = "";
          try {
            source = decodeURIComponent(encodedSource);
          } catch {
            source = node.textContent ?? "";
          }

          const renderId = `docs-mermaid-${renderKey}-${index}`;
          try {
            const { svg } = await mermaid.render(renderId, source);
            if (isCurrent) {
              node.innerHTML = svg;
            }
          } catch {
            if (isCurrent) {
              node.innerHTML = `<pre><code>${escapeHtml(source)}</code></pre>`;
            }
          }
        }),
      );
    };

    renderDiagrams().catch(() => {
      nodes.forEach((node) => {
        const encodedSource = node.dataset.mermaidSource ?? "";
        let source = "";
        try {
          source = decodeURIComponent(encodedSource);
        } catch {
          source = node.textContent ?? "";
        }
        if (isCurrent) {
          node.innerHTML = `<pre><code>${escapeHtml(source)}</code></pre>`;
        }
      });
    });

    return () => {
      isCurrent = false;
    };
  }, [currentPage.id, groupId, renderedHtml]);

  const scrollToTop = () => {
    requestAnimationFrame(() => {
      contentRef.current?.scrollTo({ top: 0 });
    });
  };

  const navigate = useCallback(
    (newGroup: DocsGroup["id"], newPage: string) => {
      setExpandedPagesByGroup((prev) => {
        const expanded = new Set(prev[newGroup] ?? []);
        expanded.add(newPage);
        return { ...prev, [newGroup]: Array.from(expanded) };
      });
      setSearchParams({ group: newGroup, page: newPage });
      setActiveAnchor(null);
      setMobileNavOpen(false);
      scrollToTop();
    },
    [setSearchParams],
  );

  const scrollToAnchor = useCallback((anchor: string) => {
    setActiveAnchor(anchor);
    setMobileNavOpen(false);
    setTimeout(() => {
      document.getElementById(anchor)?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 20);
  }, []);

  const togglePage = useCallback(
    (targetPageId: string) => {
      setExpandedPagesByGroup((prev) => {
        const expanded = new Set([...(prev[groupId] ?? []), currentPage.id]);
        if (expanded.has(targetPageId)) {
          expanded.delete(targetPageId);
        } else {
          expanded.add(targetPageId);
        }
        if (targetPageId === currentPage.id) {
          expanded.add(targetPageId);
        }
        return { ...prev, [groupId]: Array.from(expanded) };
      });
    },
    [currentPage.id, groupId],
  );

  const selectAnchor = useCallback(
    (targetGroupId: DocsGroup["id"], targetPageId: string, anchor: string) => {
      setExpandedPagesByGroup((prev) => {
        const expanded = new Set(prev[targetGroupId] ?? []);
        expanded.add(targetPageId);
        return { ...prev, [targetGroupId]: Array.from(expanded) };
      });
      if (targetGroupId !== groupId || targetPageId !== currentPage.id) {
        setSearchParams({ group: targetGroupId, page: targetPageId });
        setActiveAnchor(anchor);
        setMobileNavOpen(false);
        setTimeout(() => scrollToAnchor(anchor), 80);
        return;
      }
      scrollToAnchor(anchor);
    },
    [currentPage.id, groupId, scrollToAnchor, setSearchParams],
  );

  const handleContentClick = useCallback(
    (event: MouseEvent<HTMLDivElement>) => {
      const link = (event.target as HTMLElement).closest("a");
      if (!link) return;
      const page = link.dataset.page;
      const anchor = link.dataset.anchor;
      const targetGroup =
        link.dataset.group === "internal" || link.dataset.group === "user"
          ? link.dataset.group
          : groupId;
      if (page) {
        event.preventDefault();
        if (anchor) {
          selectAnchor(targetGroup, page, anchor);
        } else {
          navigate(targetGroup, page);
        }
      } else if (anchor) {
        event.preventDefault();
        scrollToAnchor(anchor);
      }
    },
    [groupId, navigate, scrollToAnchor, selectAnchor],
  );

  const sidebar = (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <div className="grid shrink-0 grid-cols-2 gap-1 rounded-lg bg-muted p-1">
        {DOC_GROUPS.map((group) => (
          <button
            key={group.id}
            className={cn(
              "flex items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-medium transition-colors",
              group.id === groupId
                ? "bg-card text-primary shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
            onClick={() => navigate(group.id, "index")}
          >
            {group.id === "user" ? <BookOpen className="h-3.5 w-3.5" /> : <Cpu className="h-3.5 w-3.5" />}
            {group.label}
          </button>
        ))}
      </div>
      <DocsNav
        group={currentGroup}
        currentPage={currentPage}
        activeAnchor={activeAnchor}
        expandedPageIds={expandedPageIds}
        onSelectPage={(id) => navigate(groupId, id)}
        onTogglePage={togglePage}
        onSelectAnchor={(pageId, anchor) => selectAnchor(groupId, pageId, anchor)}
      />
    </div>
  );

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <PageHeader
        className="shrink-0"
        title="Documentation"
        description="User guide and internal architecture reference for webcalyzer."
      />

      <div className="min-h-0 flex-1 overflow-hidden p-4 sm:p-6">
      <div className="mx-auto flex h-full min-h-0 w-full max-w-7xl flex-col gap-5 lg:grid lg:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="hidden h-full min-h-0 overflow-hidden rounded-lg border border-border/70 bg-sidebar p-3 lg:block">
          {sidebar}
        </aside>

        <div className="shrink-0 lg:hidden">
          <Button
            variant="outline"
            className="w-full justify-start"
            onClick={() => setMobileNavOpen((open) => !open)}
          >
            {mobileNavOpen ? <X className="mr-2 h-4 w-4" /> : <Menu className="mr-2 h-4 w-4" />}
            {mobileNavOpen ? "Close documentation navigation" : "Open documentation navigation"}
          </Button>
          {mobileNavOpen && (
            <div className="mt-3 max-h-[45vh] overflow-y-auto rounded-lg border border-border/70 bg-sidebar p-3">
              {sidebar}
            </div>
          )}
        </div>

        <main
          ref={contentRef}
          className="min-h-0 min-w-0 flex-1 overflow-y-auto rounded-lg border border-border/70 bg-card/40 px-5 py-6 sm:px-8 lg:h-full"
          onClick={handleContentClick}
        >
          <article
            className="docs-prose"
            dangerouslySetInnerHTML={{ __html: renderedHtml }}
          />
        </main>
      </div>
      </div>
    </div>
  );
}
