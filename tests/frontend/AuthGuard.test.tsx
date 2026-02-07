import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";

// Mock auth 模块（路径相对于测试文件所在目录）
vi.mock("../../frontend/src/services/auth", () => ({
  isAuthenticated: vi.fn(),
}));

import { isAuthenticated } from "../../frontend/src/services/auth";
import { AuthGuard } from "../../frontend/src/components/AuthGuard";

describe("AuthGuard", () => {
  it("redirects to login when not authenticated", () => {
    (isAuthenticated as ReturnType<typeof vi.fn>).mockReturnValue(false);
    render(
      <MemoryRouter>
        <AuthGuard>
          <div>Protected</div>
        </AuthGuard>
      </MemoryRouter>
    );
    expect(screen.queryByText("Protected")).not.toBeInTheDocument();
  });

  it("renders children when authenticated", () => {
    (isAuthenticated as ReturnType<typeof vi.fn>).mockReturnValue(true);
    render(
      <MemoryRouter>
        <AuthGuard>
          <div>Protected</div>
        </AuthGuard>
      </MemoryRouter>
    );
    expect(screen.getByText("Protected")).toBeInTheDocument();
  });
});
