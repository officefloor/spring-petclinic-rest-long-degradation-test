package org.springframework.samples.petclinic.acceptance;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.time.LocalDate;
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

	/** A unique 10-digit telephone starting with 2 (seed uses 6xxxxxxxxx). */
	protected String uniqueTelephone() {
		return String.format("2%09d", seq());
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

	protected ResultActions getOwner(int id) throws Exception {
		return mvc.perform(get("/api/owners/" + id));
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
}
