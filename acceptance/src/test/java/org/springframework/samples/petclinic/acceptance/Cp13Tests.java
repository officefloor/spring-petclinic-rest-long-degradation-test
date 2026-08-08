package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import tools.jackson.databind.node.ObjectNode;

/** namesake-count: Return 'namesakeCount' = the number of existing owners (before this create) sharing the sa... */
@Tag("cp13")
class Cp13Tests extends AcceptanceBase {

	@Test
	void coreCountsNamesakes() throws Exception {
		// The two owners share firstName+lastName (the namesake key) but use DIFFERENT postcodes so
		// they never fall into the same computed household once keys householdId on
		// (lastName, postcode) -- otherwise the later household-duplicate block would 409 the setup.
		String first = "Ann", last = uniqueLastName();
		ObjectNode a = ownerNode();
		a.put("firstName", first); a.put("lastName", last); a.put("postcode", "2000");
		createOwnerOk(a);
		ObjectNode b = ownerNode();
		b.put("firstName", first); b.put("lastName", last); b.put("postcode", "2001");
		int id = createOwnerOk(b);
		getOwner(id).andExpect(jsonPath("$.namesakeCount").value(1));
	}
}
