"""A stand-in for SAP Commerce, so a real compiler can read the generated code. [1.37]

The static rung parses every generated file and checks that each type it names is one we
recognise. That catches invented types and misses everything a *compiler* catches:
signatures, overrides, generics, and — the one that started this — a type used without
being imported. `DefaultAcmeLoyaltyAccountDao` referenced `AcmeLoyaltyAccountModel` with
no import at all. The name resolved against a known set, so the static rung passed it, and
`javac` would have rejected it on the first line that used it.

Getting a compiler onto the output normally needs the licensed platform. It does not have
to: `javac` needs *declarations*, not implementations. So this emits two sets of stubs —

**The API surface.** Around thirty `de.hybris.platform.*` types the emitters reference,
declared with the members the generated code actually calls. Hand-written, because the
whole value of the exercise depends on these signatures being right.

**The generated models.** Hybris builds `AcmeLoyaltyAccountModel` from `items.xml` at
build time. This migration *writes* that `items.xml`, so it knows exactly which model
classes the platform would generate and can declare them itself — which is what makes the
approach work at all rather than stopping at the first `*Model` reference.

**The limit, which is the point.** Compiling against a stand-in proves the output is
consistent with *the surface declared here*. Where a stub's signature is wrong, `javac`
accepts wrong code exactly as confidently as right code, and the failure has moved from
the parser into this file. That is why the rung is `typechecked` and not `compiled`, and
why `assurance.CLAIMS` says in as many words that it is not yet evidence the code builds.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

#: Where model classes are declared. Hybris generates them into the extension's own
#: `<packageroot>.model` by convention, and the DAO emitter names them unqualified — so
#: this is also the package the generated code has to import them from.
MODEL_SUBPACKAGE = "model"

#: The API surface, as source. FQN → the declaration body, with only the members the
#: emitters actually use. Deliberately narrow: every member here is a claim about SAP's
#: API that nothing in this repository can check, so the fewer the better.
_API: dict[str, str] = {
    "de.hybris.platform.servicelayer.search.SearchResult": """
public interface SearchResult<T>
{
    java.util.List<T> getResult();
    int getCount();
    int getTotalCount();
}""",
    "de.hybris.platform.servicelayer.search.FlexibleSearchQuery": """
public class FlexibleSearchQuery
{
    public FlexibleSearchQuery(final String query) { }
    public void addQueryParameter(final String name, final Object value) { }
    public void setCount(final int count) { }
    public void setNeedTotal(final boolean needTotal) { }
    public void setStart(final int start) { }
}""",
    "de.hybris.platform.servicelayer.search.FlexibleSearchService": """
public interface FlexibleSearchService
{
    <T> de.hybris.platform.servicelayer.search.SearchResult<T> search(
            de.hybris.platform.servicelayer.search.FlexibleSearchQuery query);
    <T> T searchUnique(de.hybris.platform.servicelayer.search.FlexibleSearchQuery query);
}""",
    "de.hybris.platform.core.model.ItemModel": """
public class ItemModel
{
    public Object getPk() { return null; }
}""",
    "de.hybris.platform.servicelayer.model.ModelService": """
public interface ModelService
{
    void save(Object model);
    void saveAll();
    void remove(Object model);
    void refresh(Object model);
    <T> T create(Class<T> type);
}""",
    "de.hybris.platform.servicelayer.session.SessionService": """
public interface SessionService
{
    Object getAttribute(String key);
    void setAttribute(String key, Object value);
}""",
    "de.hybris.platform.servicelayer.user.UserService": """
public interface UserService
{
    Object getCurrentUser();
}""",
    "de.hybris.platform.servicelayer.media.MediaService": """
public interface MediaService
{
    byte[] getDataFromMedia(Object media);
}""",
    "de.hybris.platform.servicelayer.config.ConfigurationService": """
public interface ConfigurationService
{
    org.apache.commons.configuration.Configuration getConfiguration();
}""",
    "org.apache.commons.configuration.Configuration": """
public interface Configuration
{
    String getString(String key);
    String getString(String key, String defaultValue);
    int getInt(String key, int defaultValue);
    double getDouble(String key, double defaultValue);
    boolean getBoolean(String key, boolean defaultValue);
}""",
    "de.hybris.platform.core.Registry": """
public final class Registry
{
    public static Object getApplicationContext() { return null; }
}""",
    # ── interceptors ──
    "de.hybris.platform.servicelayer.interceptor.InterceptorContext": """
public interface InterceptorContext
{
    boolean isNew(Object model);
    boolean isModified(Object model);
}""",
    "de.hybris.platform.servicelayer.interceptor.InterceptorException": """
public class InterceptorException extends Exception
{
    public InterceptorException(final String message) { super(message); }
}""",
    "de.hybris.platform.servicelayer.interceptor.PrepareInterceptor": """
public interface PrepareInterceptor<T>
{
    void onPrepare(T model,
                   de.hybris.platform.servicelayer.interceptor.InterceptorContext ctx)
            throws de.hybris.platform.servicelayer.interceptor.InterceptorException;
}""",
    "de.hybris.platform.servicelayer.interceptor.ValidateInterceptor": """
public interface ValidateInterceptor<T>
{
    void onValidate(T model,
                    de.hybris.platform.servicelayer.interceptor.InterceptorContext ctx)
            throws de.hybris.platform.servicelayer.interceptor.InterceptorException;
}""",
    "de.hybris.platform.servicelayer.interceptor.InitDefaultsInterceptor": """
public interface InitDefaultsInterceptor<T>
{
    void onInitDefaults(T model,
                        de.hybris.platform.servicelayer.interceptor.InterceptorContext ctx)
            throws de.hybris.platform.servicelayer.interceptor.InterceptorException;
}""",
    "de.hybris.platform.servicelayer.interceptor.LoadInterceptor": """
public interface LoadInterceptor<T>
{
    void onLoad(T model,
                de.hybris.platform.servicelayer.interceptor.InterceptorContext ctx)
            throws de.hybris.platform.servicelayer.interceptor.InterceptorException;
}""",
    "de.hybris.platform.servicelayer.interceptor.RemoveInterceptor": """
public interface RemoveInterceptor<T>
{
    void onRemove(T model,
                  de.hybris.platform.servicelayer.interceptor.InterceptorContext ctx)
            throws de.hybris.platform.servicelayer.interceptor.InterceptorException;
}""",
    # ── cronjob ──
    "de.hybris.platform.cronjob.enums.CronJobResult": """
public enum CronJobResult { SUCCESS, FAILURE, ERROR, UNKNOWN }""",
    "de.hybris.platform.cronjob.enums.CronJobStatus": """
public enum CronJobStatus { FINISHED, RUNNING, ABORTED, PAUSED, UNKNOWN }""",
    "de.hybris.platform.cronjob.model.CronJobModel": """
public class CronJobModel extends de.hybris.platform.core.model.ItemModel
{
    public String getCode() { return null; }
}""",
    "de.hybris.platform.servicelayer.cronjob.PerformResult": """
public class PerformResult
{
    public PerformResult(final de.hybris.platform.cronjob.enums.CronJobResult result,
                         final de.hybris.platform.cronjob.enums.CronJobStatus status) { }
}""",
    "de.hybris.platform.servicelayer.cronjob.AbstractJobPerformable": """
public abstract class AbstractJobPerformable<T extends de.hybris.platform.cronjob.model.CronJobModel>
{
    public abstract de.hybris.platform.servicelayer.cronjob.PerformResult perform(T cronJob);
    public boolean isAbortable() { return false; }
    protected boolean clearAbortRequestedIfNeeded(final T cronJob) { return false; }
}""",
    # ── events ──
    "de.hybris.platform.servicelayer.event.events.AbstractEvent": """
public abstract class AbstractEvent
{
    public Object getSource() { return null; }
}""",
    "de.hybris.platform.servicelayer.event.impl.AbstractEventListener": """
public abstract class AbstractEventListener<T extends de.hybris.platform.servicelayer.event.events.AbstractEvent>
{
    protected abstract void onEvent(T event);
}""",
    "de.hybris.platform.servicelayer.event.EventService": """
public interface EventService
{
    void publishEvent(de.hybris.platform.servicelayer.event.events.AbstractEvent event);
}""",
    "de.hybris.platform.core.GenericItem": """
public class GenericItem extends de.hybris.platform.core.model.ItemModel { }""",
}

#: Third-party annotations the emitters use. Declared rather than pulled in, so the stub
#: tree needs nothing from a package manager.
_ANNOTATIONS = {
    "org.springframework.beans.factory.annotation.Required":
        "public @interface Required { }",
    "org.springframework.beans.factory.annotation.Autowired":
        "public @interface Autowired { }",
    "javax.annotation.Resource":
        "public @interface Resource { String name() default \"\"; }",
}

_ITEMTYPE = re.compile(r'<itemtype\s+code="(\w+)"')
_GENERATE_FALSE = re.compile(r'generate="false"')


def model_names(items_xml: str) -> list[str]:
    """The model classes the platform would generate from this `items.xml`.

    Only the types it is asked to generate: a type declared `generate="false"` is an
    *extension of a platform type*, whose model class the platform already ships, so
    declaring our own would collide with the real one on a licensed build.
    """
    out = []
    for block in re.split(r"(?=<itemtype\s)", items_xml or ""):
        m = _ITEMTYPE.search(block)
        if not m:
            continue
        head = block[:block.find(">") + 1] if ">" in block else block
        if _GENERATE_FALSE.search(head):
            continue
        out.append(f"{m.group(1)}Model")
    return sorted(set(out))


def _write(root: Path, fqn: str, body: str) -> Path:
    pkg, _, name = fqn.rpartition(".")
    d = root.joinpath(*pkg.split("."))
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{name}.java"
    path.write_text(f"package {pkg};\n{body.strip()}\n", encoding="utf-8")
    return path


def write_stubs(root: Path, *, items_xml: str = "", model_package: str = "") -> list[Path]:
    """Emit the whole stand-in tree. Returns the files written."""
    written = [_write(root, fqn, body) for fqn, body in _API.items()]
    written += [_write(root, fqn, body) for fqn, body in _ANNOTATIONS.items()]

    for name in model_names(items_xml):
        # A generated model carries the type's attributes as getters and setters. The
        # bodies do not matter to a compiler; the *presence* of the class does, and it is
        # what every DAO and service in the output refers to.
        written.append(_write(
            root, f"{model_package}.{name}" if model_package else name,
            f"public class {name} extends de.hybris.platform.core.model.ItemModel {{ }}"))
    return written


def compile_tree(extension_root, *, items_xml: str = "", model_package: str = "",
                 java_home: str = "") -> dict:
    """Compile the generated extension against the stand-in. [1.37]

    Returns `{ran, rung, success, files, issues, message}`. `ran=False` when no compiler
    is available, which is a fact about the machine rather than about the output — the
    caller keeps whatever rung it had.
    """
    from src import assurance

    javac = shutil.which("javac", path=java_home or None) or shutil.which("javac")
    root = Path(extension_root)
    sources = sorted(root.rglob("*.java"))
    if not javac:
        return {"ran": False, "rung": assurance.STATIC, "success": False, "files": 0,
                "issues": [], "message": "No Java compiler on this machine, so the output "
                                         "was checked statically and not compiled."}
    if not sources:
        return {"ran": False, "rung": assurance.NONE, "success": False, "files": 0,
                "issues": [], "message": "No generated Java to compile."}

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        stub_src, classes = tmp / "stubs", tmp / "classes"
        classes.mkdir()
        write_stubs(stub_src, items_xml=items_xml, model_package=model_package)
        r = subprocess.run(
            [javac, "-nowarn", "-proc:none", "-d", str(classes),
             *[str(p) for p in sorted(stub_src.rglob("*.java"))],
             *[str(p) for p in sources]],
            capture_output=True, text=True, timeout=300)

    issues = _parse_javac(r.stderr, root)
    ok = r.returncode == 0
    return {
        "ran": True,
        "rung": assurance.TYPECHECKED if ok else assurance.STATIC,
        "success": ok,
        "files": len(sources),
        "issues": issues,
        "message": (f"{len(sources)} generated file(s) compiled against a stand-in for the "
                    "platform. No licensed platform was involved, so this establishes "
                    "internal consistency rather than that the code builds."
                    if ok else
                    f"{len(issues)} compile error(s) in {len(sources)} generated file(s), "
                    "against a stand-in for the platform."),
    }


_JAVAC_LINE = re.compile(r"^(?P<file>[^:\n]+\.java):(?P<line>\d+): error: (?P<msg>.*)$",
                         re.M)


def _parse_javac(stderr: str, root: Path) -> list[dict]:
    """`javac` diagnostics as findings, in the shape every other checker returns."""
    out = []
    for m in _JAVAC_LINE.finditer(stderr or ""):
        path = Path(m.group("file"))
        try:
            rel = str(path.relative_to(root))
        except ValueError:
            rel = path.name
        out.append({
            "rule": "compile_error", "file": rel, "line": int(m.group("line")),
            "severity": "critical", "message": m.group("msg").strip(),
            "fix": "The compiler rejected this. Where the stand-in API is at fault the "
                   "stub is wrong and the generated code may be fine — check which "
                   "before changing the emitter.",
        })
    return out
