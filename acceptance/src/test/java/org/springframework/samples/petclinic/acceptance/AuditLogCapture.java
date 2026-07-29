package org.springframework.samples.petclinic.acceptance;

import java.util.List;

import org.slf4j.LoggerFactory;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;

/**
 * Captures events published to the dedicated {@code AUDIT} logger so audit
 * side-effects can be asserted without an implementation-specific hook.
 *
 * <pre>{@code
 * try (AuditLogCapture audit = new AuditLogCapture()) {
 *     createOwnerOk(validOwner());
 *     assertThat(audit.anyContains("...")).isTrue();
 * }
 * }</pre>
 *
 * Assumes the logging backend is Logback (the Spring Boot default). If a
 * checkpoint logs to a differently-named logger, adjust the name here.
 */
public final class AuditLogCapture implements AutoCloseable {

	private final Logger logger;

	private final ListAppender<ILoggingEvent> appender = new ListAppender<>();

	public AuditLogCapture() {
		this("AUDIT");
	}

	public AuditLogCapture(String loggerName) {
		this.logger = (Logger) LoggerFactory.getLogger(loggerName);
		this.appender.start();
		this.logger.addAppender(this.appender);
	}

	public List<String> messages() {
		return this.appender.list.stream().map(ILoggingEvent::getFormattedMessage).toList();
	}

	public boolean anyContains(String... substrings) {
		return messages().stream().anyMatch(m -> {
			for (String s : substrings) {
				if (!m.contains(s)) {
					return false;
				}
			}
			return true;
		});
	}

	/** True if some event at the given level (e.g. "WARN") contains all substrings. */
	public boolean anyAtLevel(String level, String... substrings) {
		return this.appender.list.stream()
				.filter(e -> e.getLevel().toString().equalsIgnoreCase(level))
				.map(ILoggingEvent::getFormattedMessage)
				.anyMatch(m -> {
					for (String s : substrings) {
						if (!m.contains(s)) {
							return false;
						}
					}
					return true;
				});
	}

	public int count() {
		return this.appender.list.size();
	}

	@Override
	public void close() {
		this.logger.detachAppender(this.appender);
	}
}
