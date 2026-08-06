package org.springframework.samples.petclinic.acceptance;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;
import org.springframework.transaction.annotation.Transactional;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

/**
 * Experimenter-owned, black-box acceptance base for PetClinic-Evolve.
 *
 * <p>Every checkpoint is a business rule on the ONE endpoint {@code POST /api/owners};
 * tests create owners and read fields back via {@code GET /api/owners/{id}}, so the
 * Spring and OfficeFloor arms are judged by identical externals.
 *
 * <p>Isolation: {@code @Transactional} rolls each test back, so count/quota rules
 * (membership number, per-day cap, per-city cap, "most common city") see only the
 * seed data plus what the test itself creates — deterministic without polluting
 * other tests. {@code @WithMockUser} authenticates as a fixed admin so the audit
 * rules can assert a known user name.
 *
 * <p>Cumulative-safety convention: {@link #ownerNode()} returns a FULLY UNIQUE
 * owner, which every rule accepts (no duplicate, no quota) at every checkpoint;
 * tests then override only the fields needed to trigger a specific rule. Reject
 * cases use data that stays rejected under all later (broader) rules.
 */
@SpringBootTest
@AutoConfigureMockMvc
@Transactional
@WithMockUser(username = "acceptance-admin", roles = {"OWNER_ADMIN", "VET_ADMIN", "ADMIN"})
public abstract class AcceptanceBase {

	private static final AtomicInteger SEQ = new AtomicInteger(0);

	@Autowired
	protected MockMvc mvc;

	@Autowired
	protected ObjectMapper om;

	protected int seq() {
		return SEQ.incrementAndGet();
	}

	// --- unique generators (avoid colliding with seed data or other tests) ---

	/** Encode n as a lowercase letter string (1->a, 26->z, 27->aa), so generated
	 *  names satisfy the base app's letters-only owner-name pattern. */
	protected String letters(int n) {
		StringBuilder sb = new StringBuilder();
		for (int x = Math.max(n, 1); x > 0; x /= 26) {
			x--;
			sb.insert(0, (char) ('a' + x % 26));
		}
		return sb.toString();
	}

	/** Unique, letters-only surname (starts with "Sur"). */
	protected String uniqueLastName() {
		return "Sur" + letters(seq());
	}

	protected String uniqueAddress() {
		return seq() + " Test Street";
	}

	protected String uniqueCity() {
		return "Town" + seq();
	}

	/** A unique 10-digit AU mobile ('04XXXXXXXX'). Chosen so the ONE payload stays valid across the
	 *  whole telephone rule chain: 10 digits satisfies the early normalize-to-10 rule; dropping the
	 *  leading '0' yields 9 national digits, which is exactly what the later E.164 '+61' form and the
	 *  per-country length rule (+61 => 9 national digits) require. Distinct from the +1 NANP seed data. */
	protected String uniqueTelephone() {
		return String.format("04%08d", seq());
	}

	protected String uniqueEmail() {
		return "owner" + seq() + "@example.test";
	}

	protected String today() {
		return LocalDate.now().toString();
	}

	// --- payloads -----------------------------------------------------------

	/** A fully valid, fully unique owner — accepted by every rule at every checkpoint. */
	protected ObjectNode ownerNode() {
		ObjectNode o = om.createObjectNode();
		o.put("firstName", "Test");
		o.put("lastName", uniqueLastName());
		o.put("address", uniqueAddress());
		o.put("city", uniqueCity());
		o.put("telephone", uniqueTelephone());
		return o;
	}

	/** Owner payload plus a postcode. "2000" is in the NSW range and is accepted by cities with no
	 *  known region (the permissive default), so it stays valid for the random cities ownerNode() makes. */
	protected ObjectNode withPostcode(ObjectNode o) {
		o.put("postcode", "2000");
		return o;
	}

	/** Owner with a STRUCTURED address (addressLine1 / city / postcode) for the later
	 *  checkpoints that replace the flat 'address' input with structured fields. */
	protected ObjectNode structuredOwner() {
		ObjectNode o = ownerNode();
		o.remove("address");
		o.put("addressLine1", seq() + " Test Street");
		o.put("postcode", "2000");
		return o;
	}

	// --- requests -----------------------------------------------------------

	protected String json(JsonNode node) {
		try {
			return om.writeValueAsString(node);
		}
		catch (Exception e) {
			throw new RuntimeException(e);
		}
	}

	protected ResultActions createOwner(JsonNode body) throws Exception {
		return mvc.perform(post("/api/owners").contentType(MediaType.APPLICATION_JSON)
				.content(json(body)));
	}

	protected int createOwnerOk(JsonNode body) throws Exception {
		return extractId(createOwner(body).andExpect(status().is2xxSuccessful()));
	}

	/** POST with an {@code Idempotency-Key} header (for the idempotent-create rule). */
	protected ResultActions createOwnerWithKey(JsonNode body, String key) throws Exception {
		return mvc.perform(post("/api/owners").contentType(MediaType.APPLICATION_JSON)
				.header("Idempotency-Key", key).content(json(body)));
	}

	/** Create {@code n} fully-unique owners (each accepted by every rule), all in the
	 *  SAME city — used to drive the per-city capacity/warning rules. Returns nothing;
	 *  each owner differs in name/address/telephone so only the city count accumulates. */
	protected void fillCity(String city, int n) throws Exception {
		for (int i = 0; i < n; i++) {
			ObjectNode o = ownerNode();
			o.put("city", city);
			createOwnerOk(o);
		}
	}

	/** Create {@code n} fully-unique owners (each accepted by every rule), all dated
	 *  today — used to drive the per-day create-limit / bulk-signup rules. */
	protected void createMany(int n) throws Exception {
		for (int i = 0; i < n; i++) {
			createOwnerOk(ownerNode());
		}
	}

	protected ResultActions getOwner(int id) throws Exception {
		return mvc.perform(get("/api/owners/" + id));
	}

	/** Soft-delete an owner via DELETE /api/owners/{id} (asserts 2xx). The record is retained,
	 *  flagged deleted, so the create endpoint's duplicate/identity checks ignore it. */
	protected void deleteOwner(int id) throws Exception {
		mvc.perform(delete("/api/owners/" + id)).andExpect(status().is2xxSuccessful());
	}

	/** GET the owner and return its JSON body (asserts 2xx). */
	protected JsonNode fetchOwner(int id) throws Exception {
		String body = getOwner(id).andExpect(status().is2xxSuccessful())
				.andReturn().getResponse().getContentAsString();
		return om.readTree(body);
	}

	protected int extractId(ResultActions ra) throws Exception {
		String body = ra.andReturn().getResponse().getContentAsString();
		if (body != null && !body.isBlank()) {
			JsonNode n = om.readTree(body);
			if (n.hasNonNull("id")) {
				return n.get("id").asInt();
			}
		}
		String location = ra.andReturn().getResponse().getHeader("Location");
		if (location != null && location.contains("/")) {
			return Integer.parseInt(location.substring(location.lastIndexOf('/') + 1));
		}
		throw new IllegalStateException("no id in create response: " + body);
	}

	// --- pinned reference data ------------------------------------------------
	// Shared, fixed ground truth for the LOOKUP-based rules (region, postcode,
	// timezone, holidays). The rule specs enumerate these same tables, so both
	// arms implement identical mappings and a test can assert an EXACT value
	// (e.g. locality "NSW" for Sydney) instead of merely that a field exists.

	/** City -> canonical region; anything not listed derives locality "UNKNOWN". */
	protected static final Map<String, String> CITY_REGION = Map.of(
			"Sydney", "NSW", "Melbourne", "VIC", "Brisbane", "QLD");

	/** Region -> IANA timezone. */
	protected static final Map<String, String> REGION_TIMEZONE = Map.of(
			"NSW", "Australia/Sydney", "VIC", "Australia/Melbourne", "QLD", "Australia/Brisbane");

	/** Region -> inclusive 4-digit postcode range {low, high}. */
	protected static final Map<String, int[]> REGION_POSTCODES = Map.of(
			"NSW", new int[] {2000, 2099}, "VIC", new int[] {3000, 3099}, "QLD", new int[] {4000, 4099});

	/** Fixed public holidays the business-day roll skips (year of the run). */
	protected static final Set<LocalDate> HOLIDAYS = Set.of(
			LocalDate.parse("2026-01-01"), LocalDate.parse("2026-01-26"),
			LocalDate.parse("2026-04-25"), LocalDate.parse("2026-12-25"), LocalDate.parse("2026-12-28"));

	protected String region(String city) {
		return CITY_REGION.getOrDefault(city, "UNKNOWN");
	}

	protected String timezone(String city) {
		return REGION_TIMEZONE.get(region(city));
	}

	/** A postcode valid for the pinned city (low end of its region's range). */
	protected String validPostcode(String city) {
		int[] r = REGION_POSTCODES.get(region(city));
		return r == null ? null : String.valueOf(r[0]);
	}

	/** A fully-valid owner in a PINNED city with a valid postcode, so its region,
	 *  timezone and postcode-derived values are known exactly. */
	protected ObjectNode knownOwner(String city) {
		ObjectNode o = ownerNode();
		o.put("city", city);
		o.put("postcode", validPostcode(city));
		return o;
	}

	/** Roll a date forward over weekends and pinned holidays to the next business day. */
	protected LocalDate toBusinessDay(LocalDate d) {
		while (d.getDayOfWeek() == DayOfWeek.SATURDAY || d.getDayOfWeek() == DayOfWeek.SUNDAY
				|| HOLIDAYS.contains(d)) {
			d = d.plusDays(1);
		}
		return d;
	}

	// --- computed expectations ------------------------------------------------
	// Tests replicate the spec's algorithms exactly so they can assert the precise
	// derived value. The algorithms are standard (SHA-256, Luhn) and also stated in
	// the specs, so both arms produce identical outputs.

	/** Full lower-case hex SHA-256 of the UTF-8 bytes of {@code s}. */
	protected static String sha256hex(String s) {
		try {
			byte[] digest = MessageDigest.getInstance("SHA-256").digest(s.getBytes(StandardCharsets.UTF_8));
			StringBuilder sb = new StringBuilder(digest.length * 2);
			for (byte b : digest) {
				sb.append(String.format("%02x", b));
			}
			return sb.toString();
		}
		catch (Exception e) {
			throw new RuntimeException(e);
		}
	}

	/** First {@code n} UPPER-case hex characters of SHA-256({@code s}). */
	protected static String shaHex(String s, int n) {
		return sha256hex(s).substring(0, n).toUpperCase();
	}

	/** Luhn check digit (0-9) over the digits contained in {@code s}. */
	protected static int luhn(String s) {
		int sum = 0;
		boolean dbl = true;
		for (int i = s.length() - 1; i >= 0; i--) {
			char c = s.charAt(i);
			if (c < '0' || c > '9') {
				continue;
			}
			int d = c - '0';
			if (dbl) {
				d *= 2;
				if (d > 9) {
					d -= 9;
				}
			}
			sum += d;
			dbl = !dbl;
		}
		return (10 - (sum % 10)) % 10;
	}
}
