package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import tools.jackson.databind.node.ObjectNode;

/** cp54 capacity-warning: 'capacityWarning' is true when the owner's city already holds 40-49
 *  owners (approaching the 50 hard limit). Fill a fresh city to 40, then the next owner in it warns. */
@Tag("cp54")
class Cp54Tests extends AcceptanceBase {

	@Test
	void coreWarnsWhenApproachingCapacity() throws Exception {
		String city = "Warn" + seq();
		fillCity(city, 40);
		ObjectNode o = ownerNode();
		o.put("city", city);
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.capacityWarning").value(true));
	}
}
