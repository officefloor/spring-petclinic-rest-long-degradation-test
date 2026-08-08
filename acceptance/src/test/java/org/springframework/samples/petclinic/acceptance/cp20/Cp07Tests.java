package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import tools.jackson.databind.node.ObjectNode;

/** registration-date: the effective registration date rolls off weekends to the
 * next Monday (supplied dates too). 2026-01-03 is a Saturday -> 2026-01-05 (Mon); a weekday is kept. */
@Tag("cp07")
class Cp07Tests extends AcceptanceBase {

	@Test
	void coreWeekendRollsToMonday() throws Exception {
		ObjectNode o = ownerNode();
		o.put("registrationDate", "2026-01-03"); // Saturday
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.registrationDate").value("2026-01-05"));
	}

	@Test
	void functionalityWeekdayKept() throws Exception {
		ObjectNode o = ownerNode();
		o.put("registrationDate", "2026-01-06"); // Tuesday
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.registrationDate").value("2026-01-06"));
	}
}
